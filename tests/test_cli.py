import os

from click.testing import CliRunner

from brightwheel_photos import cli as cli_module
from brightwheel_photos.cli import cli


def stub_network(monkeypatch):
    monkeypatch.setattr(cli_module, "trigger_2fa", lambda s, email, password: None)
    monkeypatch.setattr(
        cli_module, "login", lambda s, email, password, twofacode=None: None
    )
    monkeypatch.setattr(cli_module, "find_students", lambda s: [{"object_id": "stu-1"}])
    monkeypatch.setattr(
        cli_module, "find_activities", lambda s, student_id, since=None: iter([])
    )


def test_missing_email_exits_2_with_message():
    runner = CliRunner()
    result = runner.invoke(cli, ["--password", "secret"], env={"BRIGHTWHEEL_EMAIL": ""})

    assert result.exit_code == 2
    assert "Missing option '--email'" in result.output


def test_directory_env_var_precedence(tmp_path, monkeypatch):
    stub_network(monkeypatch)
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()

    env_dir = tmp_path / "from-env"
    result = runner.invoke(
        cli,
        ["--email", "a@b.com", "--password", "secret"],
        env={"BRIGHTWHEEL_DIRECTORY": str(env_dir)},
    )
    assert result.exit_code == 0
    assert env_dir.is_dir()

    flag_dir = tmp_path / "from-flag"
    result = runner.invoke(
        cli,
        ["--email", "a@b.com", "--password", "secret", "--directory", str(flag_dir)],
        env={"BRIGHTWHEEL_DIRECTORY": str(env_dir)},
    )
    assert result.exit_code == 0
    assert flag_dir.is_dir()


def test_skip_existing_flag(tmp_path, monkeypatch):
    import requests

    stub_network(monkeypatch)
    monkeypatch.chdir(tmp_path)

    activity = {
        "media": {"image_url": "https://schools.mybrightwheel.com/media/abc123.jpg"},
        "video_info": None,
        "created_at": "2024-01-02T03:04:05.000000+00:00",
        "note": None,
    }
    monkeypatch.setattr(
        cli_module,
        "find_activities",
        lambda s, student_id, since=None: iter([activity]),
    )

    def get_raises_if_called(self, *args, **kwargs):
        raise RuntimeError("network should not be reached when skipping")

    monkeypatch.setattr(requests.Session, "get", get_raises_if_called)

    os.makedirs("photos", exist_ok=True)
    with open("photos/abc123.jpg", "w") as f:
        f.write("existing")

    runner = CliRunner()

    # present: file already exists, so the network is never touched
    result = runner.invoke(
        cli, ["--email", "a@b.com", "--password", "secret", "--skip-existing"]
    )
    assert result.exit_code == 0
    assert "file exists already" in result.output

    # absent: skip_existing defaults to False, so it attempts the download
    result = runner.invoke(cli, ["--email", "a@b.com", "--password", "secret"])
    assert result.exit_code != 0
    assert isinstance(result.exception, RuntimeError)


def test_empty_password_reprompts(tmp_path, monkeypatch):
    stub_network(monkeypatch)
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()

    result = runner.invoke(cli, ["--email", "a@b.com"], input="\n\nsecret\n")

    assert result.exit_code == 0
    assert result.output.count("Password:") >= 3
