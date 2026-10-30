"""Roles an account is given, and the named scopes the code checks."""

from enum import StrEnum


class Role(StrEnum):
    OWNER = "owner"  # orchestrates everything, owners included; there is always at least one
    ADMIN = "admin"  # runs the household's assistant, but cannot touch owners
    MEMBER = "member"  # a person of the household: their own conversations, memories, tasks, connections
    GUEST = "guest"  # someone staying for a while: what the assistant knows about them, nothing else


class Scope(StrEnum):
    """What an action needs. Code checks scopes, never roles: the role table is the only place they meet."""

    ACCOUNTS_MANAGE = "accounts.manage"  # list accounts, invite, change roles, disable
    OWNERS_MANAGE = "accounts.owners.manage"  # the same on owners, and making someone an owner
    HOUSEHOLD_READ = "household.read"  # the household's people and where they are
    HOUSEHOLD_CONNECTIONS = "household.connections.manage"  # every connection, OAuth clients, shared services
    OWN_CONNECTIONS = "own.connections.manage"  # the connections of the account's own person
    SATELLITES_MANAGE = "satellites.manage"  # pair and revoke devices
    SYSTEM_READ = "system.read"  # what is plugged in, its versions and health
    JOURNAL_READ_ALL = "journal.read.all"
    JOURNAL_READ_OWN = "journal.read.own"  # what concerns the account's person, their conversations
    MEMORY_MANAGE_ALL = "memory.manage.all"
    MEMORY_MANAGE_OWN = "memory.manage.own"  # memories about the person (household-wide ones read only)
    TASKS_MANAGE = "tasks.manage"
    TASKS_MANAGE_OWN = "tasks.manage.own"  # tasks the person asked for
    WATCHES_MANAGE_ALL = "watches.manage.all"
    WATCHES_MANAGE_OWN = "watches.manage.own"  # watches kept for the person
