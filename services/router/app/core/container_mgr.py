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
