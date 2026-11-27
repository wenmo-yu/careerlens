"""Daemon control contract: file and built-in copy must not drift."""

from __future__ import annotations

import json

import pytest

from app.runtime.daemon.contract import (
    BUILTIN_COMMANDS,
    BUILTIN_ERROR_CODES,
    PROTOCOL,
    builtin_contract,
    load_contract,
)


def test_published_contract_is_used_when_present():
    contract = load_contract()
    assert contract.source.endswith("daemon-control-v1.json")
    assert contract.protocol == PROTOCOL == 1


def test_file_and_builtin_command_sets_match():
    contract = load_contract()
    builtin = builtin_contract()
    assert set(contract.commands) == set(builtin.commands) == set(BUILTIN_COMMANDS)
    for name, spec in contract.commands.items():
        assert spec.required_params == builtin.commands[name].required_params, name


def test_file_and_builtin_error_codes_match():
    contract = load_contract()
    assert contract.error_codes == BUILTIN_ERROR_CODES


def test_restart_only_allows_known_roles():
    contract = load_contract()
    assert contract.restart_roles == ("api", "worker")


def test_builtin_copy_is_self_consistent():
    builtin = builtin_contract()
    assert builtin.source == "builtin"
    assert builtin.commands["hello"].required_params == ("protocol", "client")
    assert builtin.commands["ping"].required_params == ()
    assert builtin.commands["restart"].required_params == ("role",)


def test_unsupported_contract_version_is_rejected(tmp_path, monkeypatch):
    payload = {
        "version": 99,
        "commands": [],
        "error_codes": [],
    }
    path = tmp_path / "daemon-control-v1.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setenv("CAREERLENS_DAEMON_CONTRACT", str(path))
    with pytest.raises(ValueError, match="version 99"):
        load_contract()


def test_missing_contract_falls_back_to_builtin(tmp_path, monkeypatch):
    monkeypatch.setenv("CAREERLENS_DAEMON_CONTRACT", str(tmp_path / "absent.json"))
    monkeypatch.setattr(
        "app.runtime.daemon.contract._candidate_paths",
        lambda: [tmp_path / "absent.json"],
    )
    contract = load_contract()
    assert contract.source == "builtin"
    assert contract.protocol == PROTOCOL
