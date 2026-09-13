"""Equivalent argument shapes are accepted; ambiguous ones are refused.

Every case here came from watching a model fail a chain: it sent the parsed
playbook where text was declared, an empty string where a list was, or a bare
inventory where an object was. The first two are the same document; the third is
not, and stays refused.
"""

import pytest

from ansible_mcp.operations.coercion import as_list, as_mapping, as_text, as_yaml_text
from ansible_mcp.operations.errors import UsageError

PLAYBOOK_TEXT = """\
- hosts: all
  gather_facts: false
  tasks:
    - name: Say hello
      ansible.builtin.debug:
        msg: hello
"""


def test_yaml_text_passes_through_untouched():
    assert as_yaml_text(PLAYBOOK_TEXT, "playbook") == PLAYBOOK_TEXT


def test_a_parsed_playbook_is_serialized_back():
    parsed = [{"hosts": "all", "tasks": [{"name": "Say hello", "ansible.builtin.debug": {}}]}]

    text = as_yaml_text(parsed, "playbook")

    assert text.startswith("- hosts: all")
    # Round trips: the document is what the agent meant, in the form we store.
    import yaml

    assert yaml.safe_load(text) == parsed


def test_a_single_play_given_as_a_mapping_is_accepted():
    text = as_yaml_text({"hosts": "all"}, "playbook")

    assert "hosts: all" in text


def test_a_number_where_a_playbook_belongs_is_refused():
    with pytest.raises(UsageError, match="should be YAML text"):
        as_yaml_text(42, "playbook")


def test_inventory_text_passes_through():
    assert as_text("[all]\nweb1", "inventory") == "[all]\nweb1"


def test_a_yaml_inventory_given_as_a_structure_is_serialized():
    text = as_text({"all": {"hosts": {"web1": None}}}, "inventory")

    assert "web1" in text


@pytest.mark.parametrize("value", [None, "", []])
def test_absent_and_empty_lists_mean_the_same(value):
    assert as_list(value, "tags") == []


def test_a_list_is_kept():
    assert as_list(["deploy", "smoke"], "tags") == ["deploy", "smoke"]


def test_a_comma_separated_string_becomes_a_list():
    assert as_list("deploy, smoke", "tags") == ["deploy", "smoke"]


def test_a_single_tag_as_a_string_becomes_one_element():
    assert as_list("deploy", "tags") == ["deploy"]


def test_numbers_in_a_list_are_stringified():
    assert as_list([1, 2], "tags") == ["1", "2"]


def test_a_mapping_where_a_list_belongs_is_refused():
    with pytest.raises(UsageError, match="should be a list"):
        as_list({"tag": "deploy"}, "tags")


@pytest.mark.parametrize("value", [None, "", {}])
def test_absent_and_empty_mappings_mean_the_same(value):
    assert as_mapping(value, "variables") == {}


def test_a_mapping_is_kept():
    assert as_mapping({"env": "prod"}, "variables") == {"env": "prod"}


def test_a_mapping_sent_as_json_text_is_parsed():
    assert as_mapping('{"env": "prod"}', "variables") == {"env": "prod"}


def test_a_mapping_sent_as_yaml_text_is_parsed():
    assert as_mapping("env: prod\nreplicas: 3", "variables") == {"env": "prod", "replicas": 3}


def test_a_bare_inventory_where_an_object_belongs_is_refused_with_an_example():
    # This is the real failure: the model sent the inventory itself as config.
    with pytest.raises(UsageError) as refusal:
        as_mapping("[all]\ntesthost ansible_connection=local", "config")

    message = str(refusal.value)
    assert "should be an object" in message
    assert '"inventory"' in message


def test_a_list_where_an_object_belongs_is_refused():
    with pytest.raises(UsageError, match="should be an object"):
        as_mapping(["env=prod"], "variables")
