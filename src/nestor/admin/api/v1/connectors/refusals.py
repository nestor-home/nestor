"""What refuses a connection, as the API says it: fields left empty, a client the service wants typed, the service's
own refusal, worded for people when the connector gave a reason."""

from collections.abc import Generator
from contextlib import contextmanager

from nestor.admin.api.v1.errors import ApiError
from nestor.admin.presentation import Phrasebook
from nestor.core import ProviderError
from nestor.modules.connectors import ClientRequired, FieldsMissing


@contextmanager
def refusals(words: Phrasebook) -> Generator[None]:
    try:
        yield
    except FieldsMissing as missing:
        raise ApiError(400, "fields_missing", fields=", ".join(words.text(f.label) for f in missing.fields)) from None
    except ClientRequired:
        raise ApiError(400, "client_required") from None
    except ProviderError as failure:
        if failure.reason is not None:
            raise ApiError(502, "service_refused", reason=words.text(failure.reason)) from None
        raise ApiError(502, "provider_refused", detail=str(failure)) from None
