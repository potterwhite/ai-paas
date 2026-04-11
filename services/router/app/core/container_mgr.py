#
# Copyright (c) 2026 PotterWhite
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
#
"""Docker container management — start/stop/status of GPU services."""

import docker


def get_container_status(container_names: list[str]) -> list[dict]:
    """Return status for each named container."""
    try:
        client = docker.from_env()
    except docker.errors.DockerException:
        return [{"name": n, "status": "docker_unavailable"} for n in container_names]

    results = []
    for name in container_names:
        try:
            c = client.containers.get(name)
            results.append({
                "name": name,
                "status": c.status,  # "running" | "paused" | "exited"
                "image": c.image.tags[0] if c.image.tags else "unknown",
            })
        except docker.errors.NotFound:
            results.append({"name": name, "status": "not_found"})

    return results


def stop_container(container_name: str) -> bool:
    """Stop a running container."""
    try:
        client = docker.from_env()
        container = client.containers.get(container_name)
        container.stop()
        return True
    except Exception:
        return False


def start_container(container_name: str) -> bool:
    """Start a stopped container."""
    try:
        client = docker.from_env()
        container = client.containers.get(container_name)
        container.start()
        return True
    except Exception:
        return False


def restart_container(container_name: str) -> bool:
    """Restart a container."""
    try:
        client = docker.from_env()
        container = client.containers.get(container_name)
        container.restart()
        return True
    except Exception:
        return False
