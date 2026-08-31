# Grid payload — patched `liblarana_OpticalDetector.so`

Not source. This is a build artefact so justIN worker jobs can fetch it: the jobscript
cannot embed it (justIN caps jobscripts at 64 kB) and `justin-cvmfs-upload` is
unreachable from CERN.

- Built from larana **v10_02_04** (= LARSOFT_SUITE_v10_20_09, as shipped in dunesw
  v10_20_09d01) with the late-light fix from
  [LArSoft/larana#45](https://github.com/LArSoft/larana/pull/45).
- `strip --strip-all`, 155048 bytes.
- md5: `fadf73bfaaf3ae8bec50647cd2c8bdaf`

Use by putting its directory first on `LD_LIBRARY_PATH`; the patch touches one .cxx and
no header, so it is ABI-compatible with the rest of the release.
