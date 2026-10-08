from breakwater.backends.base import Backend, Resources, RunResult


def get_backend(name: str) -> Backend:
    if name == "contree":
        from breakwater.backends.contree import ContreeBackend

        return ContreeBackend()
    if name == "docker":
        from breakwater.backends.docker import DockerBackend

        return DockerBackend()
    raise ValueError(f"unknown backend {name!r} (expected 'contree' or 'docker')")


__all__ = ["Backend", "Resources", "RunResult", "get_backend"]
