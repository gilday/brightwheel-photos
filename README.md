# Brightwheel Photos

Python script for downloading a student's photos from
[Brightwheel](https://schools.mybrightwheel.com).

My kid went to a daycare that used Brightwheel to communicate with parents and
guardians. The teachers sent plenty of photos using Brightwheel. This script
downloads them all so I can keep them.

Each photo's EXIF data includes the original creation date and any message
attached to the photo as a comment.

## Installing From Source

Create and activate virtual env

```sh
python3 -m venv venv
. venv/bin/activate
```

Install requirements

```sh
pip3 install -r requirements.txt
```

## Run

The program will exit when all the photos have been saved.
