"""Named playbooks, and what counts as a playbook."""

import pytest

from ansible_mcp.core import InvalidPlaybookError, PlaybookStore, validate_playbook

PLAYBOOK = """---
- name: Do something
  hosts: all
  tasks:
    - name: Say hello
      ansible.builtin.debug:
        msg: hello
"""


@pytest.fixture
def store(session_factory):
    return PlaybookStore(session_factory)


async def test_saving_then_reading_it_back(store):
    saved = await store.save("deploy", PLAYBOOK, description="deploys things", tags=["web"])

    stored = await store.get("deploy")

    assert saved.name == "deploy"
    assert stored.content == PLAYBOOK
    assert stored.description == "deploys things"
    assert stored.tags == ["web"]


async def test_saving_the_same_name_replaces_the_content(store):
    await store.save("deploy", PLAYBOOK)
    replaced = PLAYBOOK.replace("hello", "goodbye")

    await store.save("deploy", replaced)

    stored = await store.get("deploy")
    assert stored.content == replaced
    assert len(await store.list()) == 1


async def test_reading_something_that_was_never_saved(store):
    assert await store.get("nothing") is None


async def test_listing_is_alphabetical_and_limited(store):
    for name in ("charlie", "alpha", "bravo"):
        await store.save(name, PLAYBOOK)

    listed = await store.list(limit=2)

    assert [playbook.name for playbook in listed] == ["alpha", "bravo"]


async def test_deleting(store):
    await store.save("deploy", PLAYBOOK)

    assert await store.delete("deploy") is True
    assert await store.delete("deploy") is False
    assert await store.get("deploy") is None


@pytest.mark.parametrize(
    ("content", "complaint"),
    [
        ("", "empty"),
        ("   \n", "empty"),
        ("key: [unclosed", "not valid YAML"),
        ("just a string", "list of plays"),
        ("{a: 1}", "list of plays"),
        ("[]", "no plays"),
        ("- one\n- two", "not a mapping"),
    ],
)
def test_text_that_is_not_a_playbook_is_refused(content, complaint):
    with pytest.raises(InvalidPlaybookError, match=complaint):
        validate_playbook(content)


def test_a_well_formed_playbook_passes():
    validate_playbook(PLAYBOOK)


async def test_an_invalid_playbook_never_reaches_the_store(store):
    with pytest.raises(InvalidPlaybookError):
        await store.save("broken", "not: a: playbook:")

    assert await store.get("broken") is None
