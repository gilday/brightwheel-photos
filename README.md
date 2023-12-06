# Brightwheel Photos

Python script for downloading a student's photos and videos from
[Brightwheel](https://schools.mybrightwheel.com).

My kid went to a daycare that used Brightwheel to communicate with parents and
guardians. The teachers sent plenty of photos using Brightwheel. This script
downloads them all so I can keep them.

Each photo's EXIF data includes the original creation date and any message
attached to the photo as a comment.

## Use

Install with `pipx install brightwheel-photos`

```sh
brightwheel-photos --email <brightwheel-account-email> --password <brightwheel-account-password> --directory ~/Photos/brightwheel
```

The program will exit when all the photos have been saved.
