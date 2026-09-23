"""The person behind an action: one identity key, one display label.

Two fields that must never collapse into one (the defect that cost this
project a day, #151): ``identity`` is the stable, unique key that downstream
code joins on, while ``display_name`` is the label a human reads — and may
be ``None``.

Measured on the real corpus, which is why the fields look the way they do:

- 5.8% of commit authors have no GitHub account link; their only identifier
  is the hash of the commit email (``login`` is ``None``, ``email_hash`` is
  set). A model that requires a login is wrong.
- 149 commit author names are literally an email address, and those are
  blanked to ``None`` (#132), so ``display_name=None`` is a normal, expected
  state — not an error, and never a placeholder string.
- 16 name strings are each shared by several distinct people ("CI/CD Bot"
  is six of them, "root" five), so a name can never be the key when anything
  stronger exists, and two actors with the same ``display_name`` and
  different ``identity`` are two different people. Nothing here merges them.

``identity`` resolves as ``login -> email_hash -> name`` and is *stored*, so
an ``Actor`` is internally consistent by construction: ``__post_init__``
re-derives the key from the components and rejects a mismatch rather than
trusting the caller.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# A name that is, whole and entire, an email address is not a name: some
# contributors set `git user.name` to their address. Only a whole-value match
# — a name that merely *contains* an address is left alone, because
# attribution matters. Twin of `_is_address` in `coops.bronze.commits`; the
# two must keep recognising the same shape.
_ADDRESS_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def _is_address(value: str | None) -> bool:
    return isinstance(value, str) and bool(_ADDRESS_RE.fullmatch(value.strip()))


def identity_key(
    login: str | None,
    email_hash: str | None,
    display_name: str | None,
) -> str | None:
    """The stable, unique key for a person: ``login -> email_hash -> name``.

    A login outranks the hash because it is the account link; the hash
    outranks the name because 16 name strings in the corpus are each shared
    by several distinct people. Public because ``Member`` resolves its
    ``identity`` with the same rule — the precedence is a property of the
    domain, not of either class.
    """
    return login or email_hash or display_name


def display_name_of(name: str | None) -> str | None:
    """The label policy: an address-shaped name is not a label.

    Blank and address-shaped names become ``None`` — never a placeholder
    string, which would become a person downstream (#132).
    """
    if not name or _is_address(name):
        return None
    return name


@dataclass(frozen=True, slots=True)
class Actor:
    """One person as they appear behind a commit, issue or event.

    ``identity`` is the resolved key (see :func:`identity_key`);
    ``display_name`` is what a human reads, or ``None`` when the source
    carries no legible name. ``login``/``account_id`` are the GitHub account
    link when one exists; ``email_hash`` is the SHA-256 of the commit email
    for authors that have none.
    """

    identity: str
    display_name: str | None
    login: str | None = None
    account_id: int | None = None
    email_hash: str | None = None

    def __post_init__(self) -> None:
        if not (self.identity or "").strip():
            raise ValueError("Actor requires a non-empty identity")
        if self.display_name is not None and not self.display_name.strip():
            raise ValueError(
                "Actor.display_name must be None or non-blank, never a placeholder"
            )
        if self.identity != identity_key(
            self.login, self.email_hash, self.display_name
        ):
            raise ValueError(
                "Actor.identity must be the resolved key (login -> email_hash"
                f" -> name); got {self.identity!r} for login={self.login!r},"
                f" email_hash={self.email_hash!r},"
                f" display_name={self.display_name!r}"
            )

    @classmethod
    def resolve(
        cls,
        *,
        login: str | None = None,
        account_id: int | None = None,
        name: str | None = None,
        email_hash: str | None = None,
    ) -> Actor:
        """Build an Actor from the raw facts, applying the identity policy.

        ``name`` is the label exactly as the provider sent it; a name that is
        itself an email address becomes ``display_name=None`` and cannot
        serve as the identity key. With no login, no hash and no legible
        name there is nothing to key the person on, and the constructor's
        non-empty-identity guard raises.
        """
        login = login or None
        display_name = display_name_of(name)
        # ``or ""`` narrows the type; the constructor's blank-identity guard
        # then raises for a person no channel identifies.
        identity = identity_key(login, email_hash, display_name) or ""
        return cls(
            identity=identity,
            display_name=display_name,
            login=login,
            account_id=account_id,
            email_hash=email_hash,
        )
