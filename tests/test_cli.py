import io
import os

import piexif
import pytest
import requests
from click.testing import CliRunner
from PIL import Image

from brightwheel_photos import cli as cli_module
from brightwheel_photos.cli import cli

ENCODED_PHOTO_URL = (
    "https://cdn.mybrightwheel.com/media_images%2Fimages%2F134%2F455%2F440"
    "%2Fcover%2F0fb20b10635bce296fc4ff6ce9b4e9a4.png?alt=media"
)
ENCODED_VIDEO_URL = (
    "https://cdn.mybrightwheel.com/media_videos%2Fvideos%2F134%2F455%2F440"
    "%2F9c1f0e7b4a2d6f8e0b3c5a7d9e1f2a4b.mp4?alt=media"
)


def stub_network(monkeypatch):
    monkeypatch.setattr(cli_module, "trigger_2fa", lambda s, email, password: None)
    monkeypatch.setattr(
        cli_module, "login", lambda s, email, password, twofacode=None: None
    )
    monkeypatch.setattr(cli_module, "find_students", lambda s: [{"object_id": "stu-1"}])
    monkeypatch.setattr(
        cli_module, "find_activities", lambda s, student_id, since=None: iter([])
    )


def stub_activities(monkeypatch, *activities):
    monkeypatch.setattr(
        cli_module,
        "find_activities",
        lambda s, student_id, since=None: iter(activities),
    )


def photo_activity(url, note=None):
    return {
        "media": {"image_url": url},
        "video_info": None,
        "created_at": "2024-01-02T03:04:05.000000+00:00",
        "note": note,
    }


def video_activity(url):
    return {
        "media": None,
        "video_info": {"downloadable_url": url},
        "created_at": "2024-01-02T03:04:05.000000+00:00",
        "note": None,
    }


def image_bytes(image_format="PNG"):
    buffer = io.BytesIO()
    Image.new("RGB", (2, 2), "red").save(buffer, format=image_format)
    return buffer.getvalue()


class StubResponse:
    def __init__(self, content):
        self.content = content

    def iter_content(self, chunk_size=1):
        for start in range(0, len(self.content), chunk_size):
            yield self.content[start : start + chunk_size]


def stub_download(monkeypatch, content):
    def get(self, *args, **kwargs):
        return StubResponse(content)

    monkeypatch.setattr(requests.Session, "get", get)


def run_cli(*args):
    return CliRunner().invoke(
        cli, ["--email", "a@b.com", "--password", "secret", *args]
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


def test_photo_url_percent_encoding_is_decoded(tmp_path, monkeypatch):
    stub_network(monkeypatch)
    monkeypatch.chdir(tmp_path)
    stub_activities(monkeypatch, photo_activity(ENCODED_PHOTO_URL, note="beach day"))
    stub_download(monkeypatch, image_bytes())

    result = run_cli()

    assert result.exit_code == 0
    assert os.listdir("photos") == ["0fb20b10635bce296fc4ff6ce9b4e9a4.jpg"]


def test_photo_is_saved_with_exif_metadata(tmp_path, monkeypatch):
    stub_network(monkeypatch)
    monkeypatch.chdir(tmp_path)
    stub_activities(monkeypatch, photo_activity(ENCODED_PHOTO_URL, note="beach day"))
    stub_download(monkeypatch, image_bytes())

    result = run_cli()

    assert result.exit_code == 0
    exif = piexif.load("photos/0fb20b10635bce296fc4ff6ce9b4e9a4.jpg")
    assert exif["Exif"][piexif.ExifIFD.DateTimeOriginal] == b"2024:01:02 03:04:05"
    assert exif["0th"][piexif.ImageIFD.ImageDescription] == b"beach day"


@pytest.mark.parametrize(
    "extension, image_format", [("png", "PNG"), ("jpeg", "JPEG"), ("jpg", "JPEG")]
)
def test_photo_is_saved_as_jpeg(tmp_path, monkeypatch, extension, image_format):
    stub_network(monkeypatch)
    monkeypatch.chdir(tmp_path)
    url = f"https://cdn.mybrightwheel.com/media_images%2Fcover%2Fabc123.{extension}"
    stub_activities(monkeypatch, photo_activity(url))
    stub_download(monkeypatch, image_bytes(image_format))

    result = run_cli()

    assert result.exit_code == 0
    assert os.listdir("photos") == ["abc123.jpg"]
    with Image.open("photos/abc123.jpg") as saved:
        assert saved.format == "JPEG"


def test_video_url_percent_encoding_is_decoded(tmp_path, monkeypatch):
    stub_network(monkeypatch)
    monkeypatch.chdir(tmp_path)
    stub_activities(monkeypatch, video_activity(ENCODED_VIDEO_URL))
    stub_download(monkeypatch, b"video content")

    result = run_cli()

    assert result.exit_code == 0
    assert os.listdir("photos") == ["9c1f0e7b4a2d6f8e0b3c5a7d9e1f2a4b.mp4"]
    with open("photos/9c1f0e7b4a2d6f8e0b3c5a7d9e1f2a4b.mp4", "rb") as f:
        assert f.read() == b"video content"


def write_existing(name):
    os.makedirs("photos", exist_ok=True)
    with open(os.path.join("photos", name), "w") as f:
        f.write("existing")


def fail_on_download(monkeypatch):
    def get(self, *args, **kwargs):
        raise RuntimeError("network should not be reached when skipping")

    monkeypatch.setattr(requests.Session, "get", get)


LEGACY_PHOTO_NAME = (
    "media_images%2Fimages%2F134%2F455%2F440%2Fcover"
    "%2F0fb20b10635bce296fc4ff6ce9b4e9a4.jpg"
)
LEGACY_VIDEO_NAME = (
    "media_videos%2Fvideos%2F134%2F455%2F440" "%2F9c1f0e7b4a2d6f8e0b3c5a7d9e1f2a4b.mp4"
)


def test_skip_existing_matches_legacy_photo_name(tmp_path, monkeypatch):
    stub_network(monkeypatch)
    monkeypatch.chdir(tmp_path)
    stub_activities(monkeypatch, photo_activity(ENCODED_PHOTO_URL))
    fail_on_download(monkeypatch)
    write_existing(LEGACY_PHOTO_NAME)

    result = run_cli("--skip-existing")

    assert result.exit_code == 0
    assert "file exists already" in result.output
    assert os.listdir("photos") == [LEGACY_PHOTO_NAME]


def test_skip_existing_matches_legacy_video_name(tmp_path, monkeypatch):
    stub_network(monkeypatch)
    monkeypatch.chdir(tmp_path)
    stub_activities(monkeypatch, video_activity(ENCODED_VIDEO_URL))
    fail_on_download(monkeypatch)
    write_existing(LEGACY_VIDEO_NAME)

    result = run_cli("--skip-existing")

    assert result.exit_code == 0
    assert "file exists already" in result.output
    assert os.listdir("photos") == [LEGACY_VIDEO_NAME]


def test_skip_existing_matches_current_photo_name(tmp_path, monkeypatch):
    stub_network(monkeypatch)
    monkeypatch.chdir(tmp_path)
    stub_activities(monkeypatch, photo_activity(ENCODED_PHOTO_URL))
    fail_on_download(monkeypatch)
    write_existing("0fb20b10635bce296fc4ff6ce9b4e9a4.jpg")

    result = run_cli("--skip-existing")

    assert result.exit_code == 0
    assert "file exists already" in result.output


def test_unrelated_existing_media_is_still_downloaded(tmp_path, monkeypatch):
    stub_network(monkeypatch)
    monkeypatch.chdir(tmp_path)
    stub_activities(monkeypatch, photo_activity(ENCODED_PHOTO_URL))
    stub_download(monkeypatch, image_bytes())
    write_existing("some-other-photo.jpg")

    result = run_cli("--skip-existing")

    assert result.exit_code == 0
    assert sorted(os.listdir("photos")) == [
        "0fb20b10635bce296fc4ff6ce9b4e9a4.jpg",
        "some-other-photo.jpg",
    ]


def test_empty_password_reprompts(tmp_path, monkeypatch):
    stub_network(monkeypatch)
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()

    result = runner.invoke(cli, ["--email", "a@b.com"], input="\n\nsecret\n")

    assert result.exit_code == 0
    assert result.output.count("Password:") >= 3
