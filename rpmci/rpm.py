import contextlib
import http.server
import logging
import os
import shutil
import subprocess
import threading


def serve_directory(directory):
    os.chdir(directory)
    logging.info("Serving RPM repository at 0.0.0.0:8000")
    server_address = ("", 8000)
    httpd = http.server.HTTPServer(server_address, http.server.CGIHTTPRequestHandler)
    httpd.serve_forever()


def copy_rpms_to_cache(rpms_directory, cache_dir):
    repodir = f"{cache_dir}/repo"
    os.mkdir(repodir)
    # Copy RPMs
    for directory, dirs, files in os.walk(rpms_directory):
        for rpm in files:
            logging.info(f"Copying {directory}/{rpm} to {repodir}/{rpm}")
            shutil.copyfile(f"{directory}/{rpm}", f"{repodir}/{rpm}")

    # Generate repository metadata
    subprocess.run(["createrepo_c", repodir])

    return repodir


@contextlib.contextmanager
def serve_repository(rpms_directory, cache_dir):
    """Create a RPM repository and serve it at 0.0.0.0:8000."""
    logging.info("Creating RPM repository")
    # Create repo directory
    repodir = copy_rpms_to_cache(rpms_directory, cache_dir)
    try:
        t = threading.Thread(target=serve_directory, args=[repodir])
        t.start()
        yield None
    finally:
        # TODO: do something about the thread?
        pass