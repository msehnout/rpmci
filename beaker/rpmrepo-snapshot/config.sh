#!/bin/bash
#
# Beaker Job Configuration
#
# This script generates a Beaker Job Configuration to create new repository
# snapshots. Right now, you need to manually comment/uncomment the different
# tasksets, if you want to adjust the set of included tasks.
#
# Note that you need AWS and OpenStack credentials for these jobs to be able
# to push data out to our storage systems!
#

set -e

RPMREPO_DATE="20201028"
RPMREPO_DISTRO="Fedora-32"

RPMREPO_AWS_ACCESS_KEY_ID=""
RPMREPO_AWS_SECRET_ACCESS_KEY=""
RPMREPO_OS_APP_CRED_ID=""
RPMREPO_OS_APP_CRED_SECRET=""

if [[ -f "./creds.rpmrepo.sh" ]] ; then
        source "./creds.rpmrepo.sh"
fi

task_rpmrepo() {
        STORAGE="$1"
        PLATFORM_ID="$2"
        SNAPSHOT_ID="$3"
        BASEURL="$4"

        cat <<END
      <task name="/osbuild/rpmci/rpmrepo/snapshot">
        <fetch url="https://github.com/osbuild/rpmci/archive/main.zip#beaker/rpmrepo-snapshot"/>
        <params>
          <param name="RPMREPO_AWS_ACCESS_KEY_ID" value="${RPMREPO_AWS_ACCESS_KEY_ID}"/>
          <param name="RPMREPO_AWS_SECRET_ACCESS_KEY" value="${RPMREPO_AWS_SECRET_ACCESS_KEY}"/>
          <param name="RPMREPO_OS_APP_CRED_ID" value="${RPMREPO_OS_APP_CRED_ID}"/>
          <param name="RPMREPO_OS_APP_CRED_SECRET" value="${RPMREPO_OS_APP_CRED_SECRET}"/>

          <param name="RPMREPO_BASEURL" value="${BASEURL}"/>
          <param name="RPMREPO_PLATFORM_ID" value="${PLATFORM_ID}"/>
          <param name="RPMREPO_SNAPSHOT_ID" value="${SNAPSHOT_ID}"/>
          <param name="RPMREPO_STORAGE" value="${STORAGE}"/>
        </params>
      </task>
END
}

taskset_fedora_release() {
        VERSION="$1"
        ARCH="$2"

        task_rpmrepo \
                "anon" \
                "f${VERSION}" \
                "f${VERSION}-${ARCH}-fedora-${RPMREPO_DATE}" \
                "https://dl01.fedoraproject.org/pub/fedora/linux/releases/${VERSION}/Everything/${ARCH}/os/"
        task_rpmrepo \
                "anon" \
                "f${VERSION}" \
                "f${VERSION}-${ARCH}-fedora-modular-${RPMREPO_DATE}" \
                "https://dl01.fedoraproject.org/pub/fedora/linux/releases/${VERSION}/Modular/${ARCH}/os/"
}

taskset_fedora_updates() {
        VERSION="$1"
        ARCH="$2"

        task_rpmrepo \
                "anon" \
                "f${VERSION}" \
                "f${VERSION}-${ARCH}-updates-released-${RPMREPO_DATE}" \
                "https://dl01.fedoraproject.org/pub/fedora/linux/updates/${VERSION}/Everything/${ARCH}/"
        task_rpmrepo \
                "anon" \
                "f${VERSION}" \
                "f${VERSION}-${ARCH}-updates-released-modular-${RPMREPO_DATE}" \
                "https://dl01.fedoraproject.org/pub/fedora/linux/updates/${VERSION}/Modular/${ARCH}/"
}

taskset_fedora_devel() {
        VERSION="$1"
        ARCH="$2"

        task_rpmrepo \
                "anon" \
                "f${VERSION}" \
                "f${VERSION}-${ARCH}-devel-${RPMREPO_DATE}" \
                "https://dl01.fedoraproject.org/pub/fedora/linux/development/${VERSION}/Everything/${ARCH}/os/"
}

taskset_rhel8_release() {
        VERSION="$1"
        ARCH="$2"

        task_rpmrepo \
                "psi" \
                "el8" \
                "el8-${ARCH}-baseos-8.${VERSION}.0.r-${RPMREPO_DATE}" \
                "http://download.eng.rdu.redhat.com/rhel-8/rel-eng/RHEL-8/latest-RHEL-8.${VERSION}/compose/BaseOS/${ARCH}/os/"
        task_rpmrepo \
                "psi" \
                "el8" \
                "el8-${ARCH}-appstream-8.${VERSION}.0.r-${RPMREPO_DATE}" \
                "http://download.eng.rdu.redhat.com/rhel-8/rel-eng/RHEL-8/latest-RHEL-8.${VERSION}/compose/AppStream/${ARCH}/os/"
}

taskset_rhel8_nightly() {
        VERSION="$1"
        ARCH="$2"

        task_rpmrepo \
                "psi" \
                "el8" \
                "el8-${ARCH}-baseos-8.${VERSION}.0.n-${RPMREPO_DATE}" \
                "http://download.eng.rdu.redhat.com/rhel-8/nightly/RHEL-8/latest-RHEL-8.${VERSION}/compose/BaseOS/${ARCH}/os/"
        task_rpmrepo \
                "psi" \
                "el8" \
                "el8-${ARCH}-appstream-8.${VERSION}.0.n-${RPMREPO_DATE}" \
                "http://download.eng.rdu.redhat.com/rhel-8/nightly/RHEL-8/latest-RHEL-8.${VERSION}/compose/AppStream/${ARCH}/os/"
}

recipeset_recipe_open() {
        DESC="$1"

        cat <<END
  <recipeSet priority="Normal">
    <recipe whiteboard="RPMrepo/snapshot/recipyset - ${DESC}" ks_meta="harness='restraint beakerlib'">
      <autopick random="true"/>
      <hostRequires>
        <and>
          <system>
            <arch op="==" value="x86_64"/>
            <type value="Machine"/>
          </system>
          <diskspace op=">=" units="GiB" value="200"/>
          <not>
            <or>
              <hostname op="=" value="intel-sugarbay-do-01.ml3.eng.bos.redhat.com"/>
            </or>
          </not>
        </and>
      </hostRequires>
      <distroRequires>
        <and>
          <name op="==" value="${RPMREPO_DISTRO}"/>
        </and>
      </distroRequires>
      <partitions>
        <partition type="part" name="var/lib/rpmrepo" fs="xfs" size="150" />
      </partitions>

      <task name="/distribution/check-install" role="STANDALONE">
      </task>
END
}

recipeset_recipe_close() {
        cat <<END
    </recipe>
  </recipeSet>
END
}

job_open() {
        DESC="$1"

        cat <<END
<job retention_tag="scratch">
  <whiteboard>RPMrepo/snapshot - ${DESC}</whiteboard>
END
}

job_close() {
        cat <<END
</job>
END
}

job_open "Everything"

recipeset_recipe_open "f31"
taskset_fedora_release 31 x86_64
taskset_fedora_updates 31 x86_64
recipeset_recipe_close

recipeset_recipe_open "f32"
taskset_fedora_release 32 x86_64
taskset_fedora_updates 32 x86_64
recipeset_recipe_close

recipeset_recipe_open "f33"
taskset_fedora_devel 33 x86_64
recipeset_recipe_close

recipeset_recipe_open "rhel8.2.r"
taskset_rhel8_release 2 x86_64
taskset_rhel8_release 2 aarch64
taskset_rhel8_release 2 ppc64le
taskset_rhel8_release 2 s390x
recipeset_recipe_close

recipeset_recipe_open "rhel8.3.n"
taskset_rhel8_nightly 3 x86_64
taskset_rhel8_nightly 3 aarch64
taskset_rhel8_nightly 3 ppc64le
taskset_rhel8_nightly 3 s390x
recipeset_recipe_close

recipeset_recipe_open "rhel8.4.n"
taskset_rhel8_nightly 4 x86_64
taskset_rhel8_nightly 4 aarch64
taskset_rhel8_nightly 4 ppc64le
taskset_rhel8_nightly 4 s390x
recipeset_recipe_close

job_close
