"""Languages through the API: each account reads in its own, anonymous visitors in their browser's,
messages travel as ids with arguments and as text, and the server's catalogues are there to load."""

from pathlib import Path

from nestor.core import Event
from nestor.modules.accounts import AccountLocaleChanged, Role

from ...harness import OWNER, Harness


async def test_an_account_reads_in_the_household_language_until_it_chooses_another(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        api = await admin.api()
        me = (await api.get("/api/v1/me")).json()
        assert (
            me["locale"] == "fr" and me["account"]["locale"] is None and me["account"]["role_label"] == "propriétaire"
        )

        unknown = await api.put("/api/v1/me/locale", {"locale": "tlh"})
        assert unknown.status_code == 400 and unknown.json()["error"]["message"] == "Cette langue n'est pas disponible."
        chosen = (await api.put("/api/v1/me/locale", {"locale": "EN"})).json()
        assert chosen["locale"] == "en" and chosen["account"]["role_label"] == "owner"
        missing = await api.get("/api/v1/memories/nope")
        assert missing.json()["error"]["message"] == "This does not exist (or no longer)."
        kinds = (await api.get("/api/v1/journal/facets")).json()["kinds"]
        assert {"key": "account", "label": "Accounts", "count": 3} in kinds
        (changed,) = await admin.nestor.journal.history(AccountLocaleChanged)
        assert changed.locale == "en"
        assert (await api.put("/api/v1/me/locale", {"locale": None})).json()["locale"] == "fr"


async def test_the_household_reads_the_journal_each_in_their_language(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        await admin.account("lucie", Role.ADMIN, "lucie")
        lucie = await admin.api("lucie")
        await lucie.put("/api/v1/me/locale", {"locale": "en"})
        english = (await lucie.get("/api/v1/journal", kinds="account")).json()["items"]
        french = (await (await admin.api()).get("/api/v1/journal", kinds="account")).json()["items"]
        assert english[-1]["text"] == "Account mathis opened (owner)"
        assert french[-1]["text"] == "Compte mathis ouvert (propriétaire)"
        assert (
            english[-1]["message"]
            == french[-1]["message"]
            == {
                "id": "journal-account-created",
                "args": {"login": OWNER, "role": "owner"},
            }
        )


async def test_an_anonymous_visitor_is_answered_in_their_browsers_language(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        api = await admin.api(None)
        for header, expected in (
            ("en-GB,en;q=0.9", "Sign in to continue."),
            ("de-DE, fr;q=0.5, en;q=0.4", "Connectez-vous pour continuer."),
            ("de, *;q=0.1, en;q=0", "Connectez-vous pour continuer."),
            ("en;q=notanumber, fr", "Connectez-vous pour continuer."),
        ):
            response = await api.client.get("/api/v1/me", headers={"Accept-Language": header})
            error = response.json()["error"]
            assert (error["message_id"], error["message"]) == ("error-unauthenticated", expected), header


async def test_the_server_lists_its_languages_and_hands_out_its_catalogues(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        api = await admin.api(None)
        assert (await api.get("/api/v1/i18n")).json() == {"locales": ["en", "fr"], "default": "en", "household": "fr"}
        catalogue = await api.get("/api/v1/i18n/fr-CA")
        assert catalogue.headers["content-language"] == "fr"
        assert "journal-user-said =" in catalogue.text and "harness-mailbox-title = Messagerie" in catalogue.text
        assert (await api.get("/api/v1/i18n/ja")).headers["content-language"] == "en"


class Unheard(Event, event_type="testing.unheard"):
    note: str


class Described(Event, event_type="testing.described"):
    note: str
    flag: bool = False


async def test_a_plugin_describes_its_events_in_its_own_catalogue_or_they_show_their_type(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        await admin.nestor.journal.publish(Unheard(source="plugin", note="x"))
        await admin.nestor.journal.publish(Described(source="plugin", note="le colis"))
        items = {i["type"]: i for i in (await (await admin.api()).get("/api/v1/journal")).json()["items"]}
        unheard, described = items["testing.unheard"], items["testing.described"]
        assert unheard["message"] == {"id": "journal-other", "args": {"type": "testing.unheard"}}
        assert unheard["text"] == "testing.unheard" and unheard["kind"] == "other"
        assert described["text"] == "Un greffon a noté : le colis"
        assert described["message"] == {
            "id": "journal-testing-described",
            "args": {"note": "le colis", "type": "testing.described"},
        }


async def test_an_entry_no_installed_code_can_read_still_shows_its_type(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        await admin.nestor.database.write(
            lambda c: c.execute(
                "INSERT INTO events (id, type, version, at, source, session, payload) "
                "VALUES (?, ?, 1, ?, 's', NULL, ?)",
                ("e1", "plugin.gone", "2026-10-30T10:00:00.000000Z", '{"x": 1}'),
            )
        )
        items = (await (await admin.api()).get("/api/v1/journal", kinds="other")).json()["items"]
        gone = next(i for i in items if i["type"] == "plugin.gone")
        assert (gone["kind"], gone["text"]) == ("other", "plugin.gone")
