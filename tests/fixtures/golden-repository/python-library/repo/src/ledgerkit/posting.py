from __future__ import annotations

import attrs
from dateutil.parser import isoparse


@attrs.define(frozen=True)
class Posting:
    account: str
    amount_minor: int
    posted_at: str

    @property
    def posted(self):
        return isoparse(self.posted_at)


def balance(postings):
    return sum(posting.amount_minor for posting in postings)
