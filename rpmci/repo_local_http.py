"""rpmci/repo_local_http - Serve repository using local HTTP server

The `repo_local_http` module provides RPM repository using the built-in HTTP server
in Python standard library. This repository is provided to the steering and target
machines so that they can install requested packages.
"""
import contextlib
import http.server
import logging
import os
import shutil
import subprocess
import threading
import time


class RepoLocalHttp(contextlib.AbstractContextManager):
    """Provide RPM repository using local HTTP server."""

    def __init__(self, cache_dir, rpms_directory, repo_name, hostname, port):
        self.cache_dir = cache_dir
        self.rpms_directory = rpms_directory
        self.name = repo_name
        self.baseurl = f"http://{hostname}:{port}"
        self.port = port
        self.http_thread = None
        self.httpd = None

    def _serve_directory(self, directory, port):
        os.chdir(directory)
        server_address = ("", port)
        self.httpd = http.server.HTTPServer(server_address, http.server.CGIHTTPRequestHandler)
        logging.info("Serving RPM repository at 0.0.0.0:8000")
        self.httpd.serve_forever()

    def _copy_rpms_to_cache(self, rpms_directory):
        repodir = f"{self.cache_dir}/repo"
        os.mkdir(repodir)
        # Copy RPMs
        for directory, _dirs, files in os.walk(rpms_directory):
            for rpm in files:
                logging.info(f"Copying {directory}/{rpm} to {repodir}/{rpm}")
                shutil.copyfile(f"{directory}/{rpm}", f"{repodir}/{rpm}")

        # Generate repository metadata
        subprocess.run(["createrepo_c", repodir])

        return repodir

    def __enter__(self):
        repodir = self._copy_rpms_to_cache(self.rpms_directory)
        self.http_thread = threading.Thread(target=self._serve_directory, args=[repodir, self.port])
        self.http_thread.start()
        # Give the HTTP server time to start
        time.sleep(2)

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.httpd.shutdown()
