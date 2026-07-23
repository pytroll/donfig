# Releasing Donfig

1. checkout main branch
2. pull from repo
3. run the unittests
4. run `loghub` and update the `CHANGELOG.md` file:

   ```
   loghub pytroll/donfig --token $LOGHUB_GITHUB_TOKEN -st $(git tag --sort=-version:refname --list 'v*' | head -n 1) -plg bug "Bugs fixed" -plg enhancement "Features added" -plg documentation "Documentation changes" -plg backwards-incompatibility "Backward incompatible changes" -plg refactor "Refactoring"
   ```

   Don't forget to commit!

5. push the changelog commit to github and verify the "CI" workflow passes
6. create a github release, typing a new tag name with the new version number starting with a 'v' (eg. `v0.22.45`) — github creates the tag when the release is published. See [semver.org](http://semver.org/) on how to write a version number. The package version is derived from this tag by `hatch-vcs` at build time, so no version bump commit is needed. Equivalently, from the command line:

   ```
   gh release create v0.22.45 --title "Version 0.22.45" --generate-notes
   ```

7. verify the "Release" github workflow passes and the package appears on PyPI. On a published release the workflow builds the sdist and wheel, checks that the built version matches the tag, and uploads to PyPI via Trusted Publishing (the `pypi` environment; no API token involved).
