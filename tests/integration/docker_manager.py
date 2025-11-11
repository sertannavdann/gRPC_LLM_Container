"""
Docker Compose orchestration for integration tests.

Manages service lifecycle: build, start, health check, logs, stop.
"""

import subprocess
import time
import logging
from pathlib import Path
from typing import Optional, List

logger = logging.getLogger(__name__)


class DockerComposeManager:
    """
    Manages Docker Compose stack for integration testing.
    
    Responsibilities:
        1. Build service images
        2. Start containers
        3. Wait for health checks
        4. Collect logs on failure
        5. Clean up after tests
    """
    
    def __init__(self, compose_file: str = "docker-compose.yaml"):
        """
        Initialize manager.
        
        Args:
            compose_file: Path to docker-compose.yaml
        """
        self.compose_file = Path(compose_file)
        self.project_name = "grpc_llm_test"
        
        if not self.compose_file.exists():
            raise FileNotFoundError(f"Compose file not found: {compose_file}")
        
        # Find Docker command
        self.docker_cmd = self._find_docker()
        
        logger.info(f"DockerComposeManager initialized: {compose_file}")
        logger.info(f"Using Docker: {self.docker_cmd}")
    
    def _find_docker(self) -> str:
        """
        Find Docker executable.
        
        Returns:
            str: Path to docker command
        
        Raises:
            FileNotFoundError: If docker not found
        """
        import subprocess
        
        docker_paths = [
            "docker",
            "/usr/local/bin/docker",
            "/Applications/Docker.app/Contents/Resources/bin/docker",
        ]
        
        for path in docker_paths:
            try:
                subprocess.run(
                    [path, "--version"],
                    check=True,
                    capture_output=True,
                    timeout=5,
                )
                return path
            except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
                continue
        
        raise FileNotFoundError("Docker not found in any common location")
    
    def build(self, services: Optional[List[str]] = None, no_cache: bool = False):
        """
        Build service images.
        
        Args:
            services: List of service names to build (None = all)
            no_cache: Force rebuild without cache
        """
        cmd = [self.docker_cmd, "compose", "-f", str(self.compose_file), "build"]
        
        if no_cache:
            cmd.append("--no-cache")
        
        if services:
            cmd.extend(services)
        
        logger.info(f"Building services: {services or 'all'}")
        
        try:
            result = subprocess.run(
                cmd,
                check=True,
                capture_output=True,
                text=True,
                timeout=600,  # 10 minutes for build
            )
            logger.info("Build completed successfully")
            return result
        except subprocess.CalledProcessError as e:
            logger.error(f"Build failed: {e.stderr}")
            raise
        except subprocess.TimeoutExpired:
            logger.error("Build timeout after 10 minutes")
            raise
    
    def up(self, services: Optional[List[str]] = None, detach: bool = True):
        """
        Start services.
        
        Args:
            services: List of service names to start (None = all)
            detach: Run in background (default: True)
        """
        cmd = [
            self.docker_cmd,
            "compose",
            "-f", str(self.compose_file),
            "-p", self.project_name,
            "up",
        ]
        
        if detach:
            cmd.append("-d")
        
        if services:
            cmd.extend(services)
        
        logger.info(f"Starting services: {services or 'all'}")
        
        try:
            result = subprocess.run(
                cmd,
                check=True,
                capture_output=True,
                text=True,
                timeout=120,
            )
            logger.info("Services started successfully")
            return result
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to start services: {e.stderr}")
            raise
        except subprocess.TimeoutExpired:
            logger.error("Service start timeout")
            raise
    
    def down(self, volumes: bool = True, remove_orphans: bool = True):
        """
        Stop and remove containers.
        
        Args:
            volumes: Remove named volumes (default: True)
            remove_orphans: Remove orphan containers (default: True)
        """
        cmd = [
            self.docker_cmd,
            "compose",
            "-f", str(self.compose_file),
            "-p", self.project_name,
            "down",
        ]
        
        if volumes:
            cmd.append("-v")
        
        if remove_orphans:
            cmd.append("--remove-orphans")
        
        logger.info("Stopping services")
        
        try:
            result = subprocess.run(
                cmd,
                check=False,  # Don't fail if already stopped
                capture_output=True,
                text=True,
                timeout=60,
            )
            logger.info("Services stopped")
            return result
        except subprocess.TimeoutExpired:
            logger.warning("Service stop timeout")
    
    def ps(self) -> str:
        """
        List running containers.
        
        Returns:
            str: Container status output
        """
        cmd = [
            self.docker_cmd,
            "compose",
            "-f", str(self.compose_file),
            "-p", self.project_name,
            "ps",
        ]
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=10,
            )
            return result.stdout
        except Exception as e:
            logger.error(f"Failed to list containers: {e}")
            return ""
    
    def wait_for_service(
        self,
        service: str,
        port: int,
        timeout: int = 60,
        check_interval: int = 2,
    ) -> bool:
        """
        Wait for service to be ready by checking port.
        
        Args:
            service: Service name
            port: Port to check
            timeout: Maximum wait time in seconds
            check_interval: Check interval in seconds
        
        Returns:
            bool: True if service is ready, False if timeout
        """
        import socket
        
        start_time = time.time()
        logger.info(f"Waiting for {service} on port {port}...")
        
        while time.time() - start_time < timeout:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(1)
                result = sock.connect_ex(("localhost", port))
                sock.close()
                
                if result == 0:
                    logger.info(f"{service} is ready on port {port}")
                    return True
            except Exception as e:
                logger.debug(f"Connection attempt failed: {e}")
            
            time.sleep(check_interval)
        
        logger.error(f"{service} not ready after {timeout}s")
        return False
    
    def wait_for_health(
        self,
        service: str,
        timeout: int = 60,
        check_interval: int = 2,
    ) -> bool:
        """
        Wait for service health check to pass.
        
        Args:
            service: Service name (e.g., "orchestrator")
            timeout: Maximum wait time in seconds
            check_interval: Check interval in seconds
        
        Returns:
            bool: True if healthy, False if timeout
        """
        start_time = time.time()
        logger.info(f"Waiting for {service} health check...")
        
        # Map service names to container names
        container_name = f"{self.project_name}-{service}-1"
        
        while time.time() - start_time < timeout:
            try:
                # Check container status
                result = subprocess.run(
                    [self.docker_cmd, "inspect", "--format={{.State.Health.Status}}", container_name],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                
                status = result.stdout.strip()
                
                if status == "healthy":
                    logger.info(f"{service} is healthy")
                    return True
                elif status in ["starting", ""]:
                    logger.debug(f"{service} health: {status or 'starting'}")
                else:
                    logger.warning(f"{service} health: {status}")
            
            except subprocess.TimeoutExpired:
                logger.debug(f"Health check timeout for {service}")
            except Exception as e:
                logger.debug(f"Health check error: {e}")
            
            time.sleep(check_interval)
        
        logger.error(f"{service} health check timeout after {timeout}s")
        return False
    
    def get_logs(
        self,
        service: str,
        tail: Optional[int] = None,
        follow: bool = False,
    ) -> str:
        """
        Get container logs.
        
        Args:
            service: Service name
            tail: Number of lines to retrieve (None = all)
            follow: Stream logs (default: False)
        
        Returns:
            str: Service logs
        """
        cmd = [
            self.docker_cmd,
            "compose",
            "-f", str(self.compose_file),
            "-p", self.project_name,
            "logs",
        ]
        
        if tail:
            cmd.extend(["--tail", str(tail)])
        
        if follow:
            cmd.append("-f")
        
        cmd.append(service)
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30 if not follow else None,
            )
            return result.stdout
        except Exception as e:
            logger.error(f"Failed to get logs for {service}: {e}")
            return f"Error getting logs: {e}"
    
    def restart_service(self, service: str):
        """
        Restart a specific service.
        
        Args:
            service: Service name to restart
        """
        cmd = [
            self.docker_cmd,
            "compose",
            "-f", str(self.compose_file),
            "-p", self.project_name,
            "restart",
            service,
        ]
        
        logger.info(f"Restarting service: {service}")
        
        try:
            subprocess.run(cmd, check=True, timeout=30)
            logger.info(f"{service} restarted")
        except Exception as e:
            logger.error(f"Failed to restart {service}: {e}")
            raise
