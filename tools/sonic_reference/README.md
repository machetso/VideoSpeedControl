# Sonic reference (Media3, Java)

Regenerates the reference hashes in `tests/test_sonic.py` from Media3's original `Sonic.java`,
to prove that `native/sonic_media3/sonic_media3.c` is bit-exact.

1. `Sonic.java` from `media3-common-<version>-sources.jar`
   (https://dl.google.com/dl/android/maven2/androidx/media3/media3-common/1.11.1/media3-common-1.11.1-sources.jar),
   with `checkState` imported from `Check` instead of Guava and the checkerframework annotations removed.
2. `javac -d cls Sonic.java Check.java Run.java`
3. `python tests/test_sonic.py --regenerate PATH/TO/cls` prints the new reference table.
