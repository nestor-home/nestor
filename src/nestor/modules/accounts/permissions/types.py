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
    AGENT_READ = "agent.read"  # what the agent is doing now, its quiet hours and the messages it will send
    AGENT_CHAT = "agent.chat"  # write to the agent from the admin, in the person's own chats
    HOUSEHOLD_CONNECTIONS = "household.connections.manage"  # every connection, OAuth clients, shared services
    OWN_CONNECTIONS = "own.connections.manage"  # the connections of the account's own person
    SATELLITES_MANAGE = "satellites.manage"  # pair and revoke devices
    SYSTEM_READ = "system.read"  # what is plugged in, its versions and health
    CONFIG_MANAGE = "config.manage"  # edit the configuration and its secrets, restart the instance
    JOURNAL_READ_ALL = "journal.read.all"
    JOURNAL_READ_OWN = "journal.read.own"  # what concerns the account's person, their conversations
    MEMORY_MANAGE_ALL = "memory.manage.all"
    MEMORY_MANAGE_OWN = "memory.manage.own"  # memories about the person (household-wide ones read only)
    TASKS_MANAGE = "tasks.manage"
    TASKS_MANAGE_OWN = "tasks.manage.own"  # tasks the person asked for
    ALERTS_MANAGE_ALL = "alerts.manage.all"  # every alert
    ALERTS_MANAGE_OWN = "alerts.manage.own"  # the alerts set for the person
    MESSAGES_READ_ALL = "messages.read.all"  # every message passed on, question and confirmation waiting
    MESSAGES_READ_OWN = "messages.read.own"  # those the person sent or receives, and their own confirmations
    MEDIA_VIEW = "media.view"  # watch the satellites that film and list the person (`MediaAccess`)
    MEDIA_VIEW_ALL = "media.view.all"  # watch every satellite that films
    MEDIA_CALL = "media.call"  # call through the satellites that hear, play sound and list the person
    MEDIA_CALL_ALL = "media.call.all"  # call through every satellite that hears and plays sound
    USAGE_READ_ALL = "usage.read.all"  # what every call to a model or an executor cost, and on whose behalf
    USAGE_READ_OWN = "usage.read.own"  # what the person's own requests cost
