"""The languages the server speaks."""

from pydantic import BaseModel


class LanguagesOut(BaseModel):
    locales: list[str]  # what can be chosen (`PUT /me/locale`) and fetched below
    default: str  # what a message missing in a locale falls back to
    household: str  # the household's language: an account's until it chooses another
