# Brightwheel -> Babybuddy Sync

Python script for synchronizing data from 
[Brightwheel](https://schools.mybrightwheel.com) to a local instance of [Baby Buddy](https://github.com/babybuddy/babybuddy) based on Gilday's [Brightwheel-Photos](https://github.com/gilday/brightwheel-photos)

This script pulls the following data from Brightwheel and inserts it into Baby Buddy:
* Diaper changes
* Bottle feedings
* Solid food feedings
* Naps
* Observations (as notes)
* Check-ins, check-outs (as notes)

The synchronization is single-directional. Data from Baby Buddy is not imported into Brightwheel.

Additionally, the original capabilities from Brightwheel-Photos are maintained.

The program will exit when all all activities are synchronized and the photos have been saved.
