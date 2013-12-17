import datetime
from distutils.version import StrictVersion
import os
import seesaw
from seesaw.config import NumberConfigValue
from seesaw.externalprocess import WgetDownload
from seesaw.item import ItemInterpolation, ItemValue
from seesaw.pipeline import Pipeline
from seesaw.project import Project
from seesaw.task import SimpleTask, LimitConcurrent
from seesaw.tracker import (GetItemFromTracker, SendDoneToTracker,
    PrepareStatsForTracker, UploadWithTracker)
from seesaw.util import find_executable
import shutil
import time


# check the seesaw version
if StrictVersion(seesaw.__version__) < StrictVersion("0.1.4"):
    raise Exception("This pipeline needs seesaw version 0.1.4 or higher.")


###########################################################################
# Find a useful Wget+Lua executable.
#
# WGET_LUA will be set to the first path that
# 1. does not crash with --version, and
# 2. prints the required version string
WGET_LUA = find_executable(
    "Wget+Lua",
    ["GNU Wget 1.14.lua.20130523-9a5c"],
    [
        "./wget-lua",
        "./wget-lua-warrior",
        "./wget-lua-local",
        "../wget-lua",
        "../../wget-lua",
        "/home/warrior/wget-lua",
        "/usr/bin/wget-lua"
    ]
)

if not WGET_LUA:
    raise Exception("No usable Wget+Lua found.")


###########################################################################
# The version number of this pipeline definition.
#
# Update this each time you make a non-cosmetic change.
# It will be added to the WARC files and reported to the tracker.
VERSION = "20131217.01"
USER_AGENT = "Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/30.0.1599.101 Safari/537.36"
TRACKER_ID = 'wretch'
TRACKER_HOST = 'tracker.archiveteam.org'


###########################################################################
# This section defines project-specific tasks.
#
# Simple tasks (tasks that do not need any concurrency) are based on the
# SimpleTask class and have a process(item) method that is called for
# each item.
class PrepareDirectories(SimpleTask):
    def __init__(self, warc_prefix):
        SimpleTask.__init__(self, "PrepareDirectories")
        self.warc_prefix = warc_prefix

    def process(self, item):
        item_name = item["item_name"]
        dirname = "/".join((item["data_dir"], item_name))

        if os.path.isdir(dirname):
            shutil.rmtree(dirname)

        os.makedirs(dirname)

        item["item_dir"] = dirname
        item["warc_file_base"] = "%s-%s-%s" % (self.warc_prefix, item_name,
            time.strftime("%Y%m%d-%H%M%S"))

        open("%(item_dir)s/%(warc_file_base)s.warc.gz" % item, "w").close()


class MoveFiles(SimpleTask):
    def __init__(self):
        SimpleTask.__init__(self, "MoveFiles")

    def process(self, item):
        os.rename("%(item_dir)s/%(warc_file_base)s.warc.gz" % item,
              "%(data_dir)s/%(warc_file_base)s.warc.gz" % item)

        shutil.rmtree("%(item_dir)s" % item)


wget_args = [
    WGET_LUA,
    "-U", USER_AGENT,
    "-nv",
    "-o", ItemInterpolation("%(item_dir)s/wget.log"),
    "--lua-script", "wretch.lua",
    "--no-check-certificate",
    "--output-document", ItemInterpolation("%(item_dir)s/wget.tmp"),
    "--truncate-output",
    "-e", "robots=off",
    "--rotate-dns",
    "--recursive", "--level=inf",
    "--page-requisites",
    "--timeout", "60",
    "--tries", "inf",
    "--span-hosts",
    "--waitretry", "3600",
    "--domains", "yimg.com,wretch.cc",
    "--warc-file", ItemInterpolation("%(item_dir)s/%(warc_file_base)s"),
    "--warc-header", "operator: Archive Team",
    "--warc-header", "wretch-dld-script-version: " + VERSION,
    "--warc-header", ItemInterpolation("wretch-user: %(item_name)s"),
    ItemInterpolation("http://www.wretch.cc/album/%(item_name)s"),
    ItemInterpolation("http://www.wretch.cc/blog/%(item_name)s"),
    ItemInterpolation("http://www.wretch.cc/guestbook/%(item_name)s"),
    ItemInterpolation("http://www.wretch.cc/user/%(item_name)s"),
    ItemInterpolation("http://www.wretch.cc/friend/%(item_name)s"),
    ItemInterpolation("http://www.wretch.cc/video/%(item_name)s"),
]

if 'bind_address' in globals():
    wget_args.extend(['--bind-address', globals()['bind_address']])
    print('')
    print('*** Wget will bind address at {0} ***'.format(globals()['bind_address']))
    print('')


###########################################################################
# Initialize the project.
#
# This will be shown in the warrior management panel. The logo should not
# be too big. The deadline is optional.
project = Project(
    title="Wretch",
    project_html="""
    <img class="project-logo" alt="" src="http://archiveteam.org/images/7/76/Archiveteam1.png" height="50" />
    <h2>Wretch <span class="links"><a href="http://www.wretch.cc/">Website</a> &middot; <a href="http://%s/%s/">Leaderboard</a></span></h2>
    <p><b>Wretch</b> is killed by Yahoo!.</p>
    """ % (TRACKER_HOST, TRACKER_ID)
    , utc_deadline=datetime.datetime(2013, 12, 26, 00, 00, 1)
)

pipeline = Pipeline(
    GetItemFromTracker("http://%s/%s" % (TRACKER_HOST, TRACKER_ID), downloader,
        VERSION),
    PrepareDirectories(warc_prefix="wretch"),
    WgetDownload(
        wget_args,
        max_tries=5,
        accept_on_exit_code=[0, 8],
        env={'wretch_username': ItemInterpolation("%(item_name)s")}
    ),
    PrepareStatsForTracker(
        defaults={ "downloader": downloader, "version": VERSION },
        file_groups={
            "data": [ ItemInterpolation("%(item_dir)s/%(warc_file_base)s.warc.gz") ]
            }
    ),
    MoveFiles(),
    LimitConcurrent(NumberConfigValue(min=1, max=4, default="1",
        name="shared:rsync_threads", title="Rsync threads",
        description="The maximum number of concurrent uploads."),
        UploadWithTracker(
            "http://tracker.archiveteam.org/%s" % TRACKER_ID,
            downloader=downloader,
            version=VERSION,
            files=[
                ItemInterpolation("%(data_dir)s/%(warc_file_base)s.warc.gz")
                ],
            rsync_target_source_path=ItemInterpolation("%(data_dir)s/"),
            rsync_extra_args=[
                "--recursive",
                "--partial",
                "--partial-dir", ".rsync-tmp"
            ]
            ),
    ),
    SendDoneToTracker(
        tracker_url="http://%s/%s" % (TRACKER_HOST, TRACKER_ID),
        stats=ItemValue("stats")
    )
)
