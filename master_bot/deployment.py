# -*- coding: utf-8 -*-
import docker
import paramiko
import os
import logging
import uuid
from typing import Optional, Tuple, Dict
from config import config

logger = logging.getLogger(__name__)

class DockerManager:
    """Docker container management for VPN bots"""
    
    def __init__(self):
        try:
            self.client = docker.from_env()
            logger.info("Docker client initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Docker client: {e}")
            self.client = None
    
    def create_bot_container(self, subscription_data: Dict) -> Tuple[Optional[str], Optional[str], str]:
        """
        Create and start a VPN bot container
        
        Args:
            subscription_data: Dictionary containing bot configuration
            
        Returns:
            Tuple of (container_id, bot_url, message)
        """
        if not self.client:
            return None, None, "Docker client not available"
        
        try:
            # Generate unique container name and port
            container_name = f"vpn-bot-{subscription_data['customer_id']}-{uuid.uuid4().hex[:8]}"
            port = self._get_available_port()
            
            if not port:
                return None, None, "No available ports"
            
            # Prepare environment variables for the bot
            env_vars = {
                'BOT_TOKEN': subscription_data['bot_token'],
                'ADMIN_ID': str(subscription_data['admin_id']),
                'CHANNEL_USERNAME': subscription_data.get('channel_username', ''),
                'CHANNEL_ID': str(subscription_data.get('channel_id', 0)),
                'DB_NAME': f"bot_{subscription_data['customer_id']}.db",
                'LOG_FILE': f"bot_{subscription_data['customer_id']}.log"
            }
            
            # Create volume for persistent data
            volume_name = f"vpn-bot-data-{subscription_data['customer_id']}"
            
            try:
                volume = self.client.volumes.create(name=volume_name)
                logger.info(f"Created volume: {volume_name}")
            except docker.errors.APIError as e:
                if "already exists" not in str(e):
                    logger.error(f"Failed to create volume: {e}")
                    return None, None, f"Volume creation failed: {e}"
            
            # Container configuration
            container_config = {
                'image': config.VPN_BOT_IMAGE,
                'name': container_name,
                'environment': env_vars,
                'ports': {'8000/tcp': port},  # Internal port mapping
                'volumes': {volume_name: {'bind': '/app/data', 'mode': 'rw'}},
                'restart_policy': {'Name': 'unless-stopped'},
                'detach': True,
                'labels': {
                    'vpn-bot': 'true',
                    'customer_id': str(subscription_data['customer_id']),
                    'subscription_id': str(subscription_data.get('subscription_id', ''))
                }
            }
            
            # Create and start container
            container = self.client.containers.run(**container_config)
            
            # Wait for container to start
            container.reload()
            
            if container.status != 'running':
                logger.error(f"Container {container_name} failed to start. Status: {container.status}")
                return None, None, "Container failed to start"
            
            # Generate bot URL (assuming reverse proxy setup)
            bot_url = f"https://{config.SERVER_HOST}:{port}"
            
            logger.info(f"Successfully created container {container_name} on port {port}")
            return container.id, bot_url, "Success"
            
        except docker.errors.ImageNotFound:
            logger.error(f"Docker image {config.VPN_BOT_IMAGE} not found")
            return None, None, "Bot image not found. Please contact support."
        
        except docker.errors.APIError as e:
            logger.error(f"Docker API error: {e}")
            return None, None, f"Docker error: {e}"
        
        except Exception as e:
            logger.error(f"Unexpected error creating container: {e}")
            return None, None, f"Container creation failed: {e}"
    
    def stop_bot_container(self, container_id: str) -> bool:
        """Stop and remove bot container"""
        if not self.client:
            return False
        
        try:
            container = self.client.containers.get(container_id)
            container.stop(timeout=10)
            container.remove()
            logger.info(f"Successfully stopped and removed container {container_id}")
            return True
        except docker.errors.NotFound:
            logger.warning(f"Container {container_id} not found")
            return True  # Already removed
        except Exception as e:
            logger.error(f"Failed to stop container {container_id}: {e}")
            return False
    
    def get_container_status(self, container_id: str) -> Optional[Dict]:
        """Get container status and stats"""
        if not self.client:
            return None
        
        try:
            container = self.client.containers.get(container_id)
            stats = container.stats(stream=False)
            
            # Calculate CPU and memory usage
            cpu_usage = self._calculate_cpu_usage(stats)
            memory_usage = self._calculate_memory_usage(stats)
            
            return {
                'status': container.status,
                'cpu_usage': cpu_usage,
                'memory_usage': memory_usage,
                'created': container.attrs['Created'],
                'ports': container.ports
            }
        except docker.errors.NotFound:
            return {'status': 'not_found'}
        except Exception as e:
            logger.error(f"Failed to get container status: {e}")
            return None
    
    def _get_available_port(self, start_port: int = 8000, end_port: int = 9000) -> Optional[int]:
        """Find an available port for the container"""
        import socket
        
        for port in range(start_port, end_port):
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                result = sock.connect_ex(('localhost', port))
                if result != 0:  # Port is available
                    return port
        
        return None
    
    def _calculate_cpu_usage(self, stats: Dict) -> float:
        """Calculate CPU usage percentage from container stats"""
        try:
            cpu_delta = stats['cpu_stats']['cpu_usage']['total_usage'] - stats['precpu_stats']['cpu_usage']['total_usage']
            system_delta = stats['cpu_stats']['system_cpu_usage'] - stats['precpu_stats']['system_cpu_usage']
            number_cpus = stats['cpu_stats']['online_cpus']
            
            if system_delta > 0:
                cpu_usage = (cpu_delta / system_delta) * number_cpus * 100.0
                return round(cpu_usage, 2)
        except (KeyError, ZeroDivisionError):
            pass
        
        return 0.0
    
    def _calculate_memory_usage(self, stats: Dict) -> float:
        """Calculate memory usage in MB from container stats"""
        try:
            memory_usage = stats['memory_stats']['usage']
            memory_limit = stats['memory_stats']['limit']
            
            if memory_limit > 0:
                usage_mb = memory_usage / (1024 * 1024)
                return round(usage_mb, 2)
        except KeyError:
            pass
        
        return 0.0
    
    def list_vpn_bot_containers(self) -> list:
        """List all VPN bot containers"""
        if not self.client:
            return []
        
        try:
            containers = self.client.containers.list(
                all=True,
                filters={'label': 'vpn-bot=true'}
            )
            
            result = []
            for container in containers:
                result.append({
                    'id': container.id,
                    'name': container.name,
                    'status': container.status,
                    'customer_id': container.labels.get('customer_id'),
                    'subscription_id': container.labels.get('subscription_id'),
                    'created': container.attrs['Created']
                })
            
            return result
        except Exception as e:
            logger.error(f"Failed to list containers: {e}")
            return []

class BotDeploymentService:
    """Main service for deploying VPN bots"""
    
    def __init__(self):
        self.docker_manager = DockerManager()
    
    def deploy_bot(self, subscription_data: Dict) -> Tuple[bool, str, Optional[Dict]]:
        """
        Deploy a VPN bot for a customer
        
        Args:
            subscription_data: Customer and bot configuration data
            
        Returns:
            Tuple of (success, message, deployment_info)
        """
        logger.info(f"Starting bot deployment for customer {subscription_data['customer_id']}")
        
        # Validate subscription data
        required_fields = ['customer_id', 'bot_token', 'admin_id']
        missing_fields = [field for field in required_fields if not subscription_data.get(field)]
        
        if missing_fields:
            return False, f"Missing required fields: {', '.join(missing_fields)}", None
        
        # Create Docker container
        container_id, bot_url, message = self.docker_manager.create_bot_container(subscription_data)
        
        if not container_id:
            return False, f"Deployment failed: {message}", None
        
        # Prepare deployment info
        deployment_info = {
            'container_id': container_id,
            'bot_url': bot_url,
            'status': 'running'
        }
        
        logger.info(f"Successfully deployed bot for customer {subscription_data['customer_id']}")
        return True, "Bot deployed successfully", deployment_info
    
    def undeploy_bot(self, container_id: str) -> Tuple[bool, str]:
        """Stop and remove a bot deployment"""
        logger.info(f"Starting bot undeployment for container {container_id}")
        
        success = self.docker_manager.stop_bot_container(container_id)
        
        if success:
            logger.info(f"Successfully undeployed container {container_id}")
            return True, "Bot undeployed successfully"
        else:
            return False, "Failed to undeploy bot"
    
    def get_bot_status(self, container_id: str) -> Optional[Dict]:
        """Get status of deployed bot"""
        return self.docker_manager.get_container_status(container_id)
    
    def list_all_deployments(self) -> list:
        """List all VPN bot deployments"""
        return self.docker_manager.list_vpn_bot_containers()

# Initialize deployment service
deployment_service = BotDeploymentService()