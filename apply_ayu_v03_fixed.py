#!/usr/bin/env python3
from __future__ import annotations

import apply_ayu_v03 as base


def patch_deleted_state(text: str) -> str:
    old_global = "                updatedState.deleteMessagesWithGlobalIds(updateDeleteMessagesData.messages)"
    new_global = """                // AYU_IOS_PATCH_v0_3: keep remote-deleted cloud messages locally and remember their ids.\n                if AyuRuntimeSettings.keepDeletedMessages {\n                    AyuRuntimeSettings.markDeletedGlobalIds(updateDeleteMessagesData.messages)\n                } else {\n                    updatedState.deleteMessagesWithGlobalIds(updateDeleteMessagesData.messages)\n                }"""
    text = base.replace_all_checked(text, old_global, new_global, "deleted-global", minimum=1)

    old_channel = "                        updatedState.deleteMessages(messages.map({ MessageId(peerId: peerId, namespace: Namespaces.Message.Cloud, id: $0) }))"
    new_channel = """                        let ayuDeletedIds = messages.map({ MessageId(peerId: peerId, namespace: Namespaces.Message.Cloud, id: $0) })\n                        if AyuRuntimeSettings.keepDeletedMessages {\n                            AyuRuntimeSettings.markDeletedMessageIds(ayuDeletedIds)\n                        } else {\n                            updatedState.deleteMessages(ayuDeletedIds)\n                        }"""
    text = base.replace_all_checked(text, old_channel, new_channel, "deleted-channel-pts", minimum=1)

    old_channel_other = "                        updatedState.deleteMessages(updateDeleteChannelMessagesData.messages.map({ MessageId(peerId: peerId, namespace: Namespaces.Message.Cloud, id: $0) }))"
    new_channel_other = """                        let ayuDeletedIds = updateDeleteChannelMessagesData.messages.map({ MessageId(peerId: peerId, namespace: Namespaces.Message.Cloud, id: $0) })\n                        if AyuRuntimeSettings.keepDeletedMessages {\n                            AyuRuntimeSettings.markDeletedMessageIds(ayuDeletedIds)\n                        } else {\n                            updatedState.deleteMessages(ayuDeletedIds)\n                        }"""
    text = base.replace_all_checked(text, old_channel_other, new_channel_other, "deleted-channel-other", minimum=1)
    return text


base.patch_deleted_state = patch_deleted_state

if __name__ == "__main__":
    base.main()
