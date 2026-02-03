"""Logging configuration and setup."""

import logging
import logging.handlers
from pathlib import Path
from typing import Dict, Any, Optional
import yaml


class ComponentLogger:
    """Logger for specific components with configurable levels."""

    def __init__(self, component_name: str, config: Dict[str, Any]):
        self.component_name = component_name
        self.config = config
        self.logger = self._setup_logger()

    def _setup_logger(self) -> logging.Logger:
        """Setup logger for this component."""
        logger = logging.getLogger(f"npc_engine.{self.component_name}")
        level_name = self.config.get('level', 'INFO')
        logger.setLevel(getattr(logging, level_name))
        
        # Prevent duplicate logs in Streamlit
        logger.propagate = False
        
        # Remove existing handlers to avoid duplicates
        logger.handlers.clear()

        # Console handler
        if self.config.get('console', {}).get('enabled', True):
            console_level_name = self.config.get('console', {}).get('level', 'INFO')
            console_level = getattr(logging, console_level_name)
            
            # DEBUG PRINT
            print(f"[LOG INIT] {self.component_name}: Logger Level={level_name}, Console Level={console_level_name}")
            
            console_handler = logging.StreamHandler()
            console_handler.setLevel(console_level)
            
            # Determine formatter
            formatter_config = self.config
            if '()' in formatter_config and formatter_config['()'] == 'coloredlogs.ColoredFormatter':
                import coloredlogs
                console_formatter = coloredlogs.ColoredFormatter(
                    formatter_config.get('format', '%(asctime)s - %(name)s - %(levelname)s - %(message)s'),
                    datefmt=formatter_config.get('date_format', '%Y-%m-%d %H:%M:%S')
                )
                # Apply custom colors if specified
                colors = formatter_config.get('colors')
                if colors:
                    # Convert color strings to dict format expected by coloredlogs
                    level_styles = {}
                    for level, style in colors.items():
                        if isinstance(style, str):
                            level_styles[level] = {'color': style}
                        else:
                            level_styles[level] = style
                    console_formatter.level_styles = level_styles
            else:
                console_formatter = logging.Formatter(
                    formatter_config.get('format', '%(asctime)s - %(name)s - %(levelname)s - %(message)s'),
                    datefmt=formatter_config.get('date_format', '%Y-%m-%d %H:%M:%S')
                )
            console_handler.setFormatter(console_formatter)
            logger.addHandler(console_handler)

        # File handler
        if self.config.get('file', {}).get('enabled', True):
            log_file = self.config.get('file', {}).get('path', f'logs/{self.component_name}.log')
            log_dir = Path(log_file).parent
            log_dir.mkdir(parents=True, exist_ok=True)

            file_handler = logging.handlers.RotatingFileHandler(
                log_file,
                maxBytes=self.config.get('file', {}).get('max_size', 10485760),  # 10MB
                backupCount=self.config.get('file', {}).get('backup_count', 5)
            )
            file_handler.setLevel(getattr(logging, self.config.get('level', 'INFO')))
            file_formatter = logging.Formatter(
                self.config.get('format', '%(asctime)s - %(name)s - %(levelname)s - %(message)s'),
                datefmt=self.config.get('date_format', '%Y-%m-%d %H:%M:%S')
            )
            file_handler.setFormatter(file_formatter)
            logger.addHandler(file_handler)

        return logger

    def get_logger(self) -> logging.Logger:
        """Get the configured logger."""
        return self.logger


class LoggingManager:
    """Manages logging configuration for all components."""

    def __init__(self, config_path: str = "config/logging.yaml"):
        # Resolve config path relative to the npc_engine root (parent of 'engine' dir)
        base_dir = Path(__file__).resolve().parent.parent
        self.config_path = base_dir / config_path
        
        self.config = self._load_config()
        self.component_loggers: Dict[str, ComponentLogger] = {}

    def _load_config(self) -> Dict[str, Any]:
        """Load logging configuration from YAML."""
        if not self.config_path.exists():
            # Default config if file doesn't exist
            return {
                'global': {
                    'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    'level': 'INFO'
                },
                'components': {
                    'world': {'level': 'DEBUG'},
                    'master': {'level': 'INFO'},
                    'npc': {'level': 'WARNING'},
                    'storage': {'level': 'INFO'},
                    'gamemaster': {'level': 'DEBUG'}
                },
                'console': {'enabled': True, 'level': 'INFO'},
                'file': {'enabled': True}
            }

        with open(self.config_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)

    def get_component_logger(self, component_name: str) -> logging.Logger:
        """Get logger for a specific component."""
        if component_name not in self.component_loggers:
            component_config = self.config.get('components', {}).get(component_name, {})
            
            # Start with global config
            full_config = dict(self.config.get('global', {}))
            
            # Merge console settings
            console_config = self.config.get('console', {})
            if console_config:
                full_config['console'] = console_config
            
            # Merge file settings
            file_config = dict(self.config.get('file', {}))
            # Override file path if component specifies one
            if 'file' in component_config:
                file_config['path'] = component_config['file']
            full_config['file'] = file_config
            
            # Override other component-specific settings
            for key, value in component_config.items():
                if key not in ['file']:  # file path already handled
                    full_config[key] = value

            self.component_loggers[component_name] = ComponentLogger(component_name, full_config)

        return self.component_loggers[component_name].get_logger()

    def setup_all_loggers(self):
        """Setup loggers for all components."""
        components = ['world', 'master', 'npc', 'storage', 'gamemaster']
        for component in components:
            self.get_component_logger(component)


# Global logging manager instance
logging_manager = LoggingManager()


def get_logger(component_name: str) -> logging.Logger:
    """Get logger for a component."""
    return logging_manager.get_component_logger(component_name)


def get_component_level(component_name: str) -> str:
    """Get the logging level for a specific component from the config.
    
    Args:
        component_name: Name of the component (e.g., 'world', 'master')
        
    Returns:
        Logging level as string (e.g., 'DEBUG', 'INFO')
    """
    config = logging_manager.config
    return config.get('components', {}).get(component_name, {}).get('level', 'INFO')