RPMci
=====

RPM Based Continuous Development

The RPMci project provides a test environment and test execution for projects
that are distributed via the RPM packaging system. Furthermore, it provides
additional infrastructure aiding projects in adopting an RPM based test
environment.

At its core is the `rpmci` application, a tool that takes a project source
repository, builds its RPMs and then deploys those RPMs plus its tests suite
in a well defined virtualized environment, followed by a full run of the test
suite.

Additionally, the project provides infrastructure to build and store pinned
operating system images that are used as base for dependent test-suites. In
combination with the provided RPM repository snapshots, it allows for content
defined OS images used throughout the test environment and thus provides
reliable test results without any moving targets other than the source code of
the to-be-tested project.

### Project

 * **Website**: <https://www.osbuild.org>
 * **Bug Tracker**: <https://github.com/osbuild/rpmci/issues>

### Requirements

The requirements for this project are:

 * `python >= 3.8`

### Repository:

 - **web**:   <https://github.com/osbuild/rpmci>
 - **https**: `https://github.com/osbuild/rpmci.git`
 - **ssh**:   `git@github.com:osbuild/rpmci.git`

### License:

 - **Apache-2.0**
 - See LICENSE file for details.
