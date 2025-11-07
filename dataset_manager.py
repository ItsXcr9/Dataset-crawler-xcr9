#!/usr/bin/env python3
"""
Dataset Management and Versioning System
Manages dataset versions, provenance, and quality metrics.
"""

import os
import json
import yaml
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from datetime import datetime
import hashlib
import structlog
from git import Repo
import pandas as pd

logger = structlog.get_logger()


@dataclass
class DatasetVersion:
    """Represents a dataset version"""
    version: str
    created_at: str
    description: str
    source_versions: Dict[str, str]  # Component -> version
    statistics: Dict[str, Any]
    quality_metrics: Dict[str, float]
    provenance: Dict[str, Any]
    checksum: str


@dataclass
class DatasetRegistry:
    """Dataset registry for versioning and provenance"""
    name: str
    description: str
    versions: List[DatasetVersion]
    current_version: str
    created_at: str
    last_updated: str


class DatasetManager:
    """Professional dataset management system"""

    def __init__(self, dataset_root: str = "dataset"):
        self.dataset_root = Path(dataset_root)
        self.registry_file = self.dataset_root / "registry.yaml"
        self.versions_dir = self.dataset_root / "versions"

        # Create directories
        self.versions_dir.mkdir(parents=True, exist_ok=True)

        # Initialize or load registry
        self.registry = self.load_or_create_registry()

        # Initialize git repo for versioning
        self.init_git_repo()

        logger.info("Dataset manager initialized", dataset_root=str(dataset_root))

    def load_or_create_registry(self) -> DatasetRegistry:
        """Load existing registry or create new one"""
        if self.registry_file.exists():
            with open(self.registry_file, 'r') as f:
                data = yaml.safe_load(f)

            versions = [DatasetVersion(**v) for v in data['versions']]
            registry = DatasetRegistry(
                name=data['name'],
                description=data['description'],
                versions=versions,
                current_version=data['current_version'],
                created_at=data['created_at'],
                last_updated=data['last_updated']
            )
            return registry
        else:
            # Create new registry
            registry = DatasetRegistry(
                name="Web Crawl Dataset",
                description="Professional web crawl dataset for LLM training",
                versions=[],
                current_version="",
                created_at=datetime.utcnow().isoformat(),
                last_updated=datetime.utcnow().isoformat()
            )
            self.save_registry(registry)
            return registry

    def save_registry(self, registry: DatasetRegistry):
        """Save registry to disk"""
        data = asdict(registry)
        with open(self.registry_file, 'w') as f:
            yaml.dump(data, f, default_flow_style=False)

    def init_git_repo(self):
        """Initialize git repository for versioning"""
        try:
            if not (self.dataset_root / ".git").exists():
                repo = Repo.init(str(self.dataset_root))
                # Create .gitignore
                gitignore = self.dataset_root / ".gitignore"
                gitignore.parent.mkdir(parents=True, exist_ok=True)
                with open(gitignore, 'w') as f:
                    f.write("""# Dataset artifacts
*.parquet
*.arrow
raw/
temp/
logs/

# Python
__pycache__/
*.pyc
*.pyo
*.pyd
.Python
env/
venv/
.venv/

# OS
.DS_Store
Thumbs.db
""")
                repo.index.add([str(gitignore)])
                repo.index.commit("Initial commit: Dataset repository setup")
                logger.info("Git repository initialized")
        except Exception as e:
            logger.warning("Failed to initialize git repo", error=str(e))

    def create_version(self, description: str, statistics: Dict[str, Any],
                      quality_metrics: Dict[str, float],
                      provenance: Dict[str, Any]) -> str:
        """Create a new dataset version"""

        # Generate version number
        if self.registry.versions:
            last_version = self.registry.versions[-1].version
            major, minor = map(int, last_version.split('.'))
            new_version = f"{major}.{minor + 1}"
        else:
            new_version = "1.0"

        # Calculate checksum of current dataset
        checksum = self.calculate_dataset_checksum()

        # Create version object
        version = DatasetVersion(
            version=new_version,
            created_at=datetime.utcnow().isoformat(),
            description=description,
            source_versions={
                'crawler': self.get_component_version('crawler'),
                'processor': self.get_component_version('processor'),
                'tokenizer': self.get_component_version('tokenizer')
            },
            statistics=statistics,
            quality_metrics=quality_metrics,
            provenance=provenance,
            checksum=checksum
        )

        # Add to registry
        self.registry.versions.append(version)
        self.registry.current_version = new_version
        self.registry.last_updated = datetime.utcnow().isoformat()

        # Save registry
        self.save_registry(self.registry)

        # Create version snapshot
        self.create_version_snapshot(version)

        # Commit to git
        self.commit_version(version)

        logger.info("Created dataset version", version=new_version)
        return new_version

    def calculate_dataset_checksum(self) -> str:
        """Calculate checksum of dataset artifacts"""
        hasher = hashlib.sha256()

        # Include key dataset files
        key_files = [
            "shards/train_manifest.json",
            "shards/val_manifest.json",
            "metadata/manifest.jsonl",
            "metadata/dataset_stats.csv",
            "tokenizer_config.json"
        ]

        for file_path in key_files:
            full_path = self.dataset_root / file_path
            if full_path.exists():
                with open(full_path, 'rb') as f:
                    hasher.update(f.read())

        return hasher.hexdigest()

    def get_component_version(self, component: str) -> str:
        """Get version of a component (placeholder)"""
        # In a real system, this would check component version files
        return "1.0.0"

    def create_version_snapshot(self, version: DatasetVersion):
        """Create a snapshot of the current dataset state"""
        version_dir = self.versions_dir / version.version
        version_dir.mkdir(exist_ok=True)

        # Copy key metadata files
        metadata_files = [
            "metadata/manifest.jsonl",
            "metadata/dataset_stats.csv",
            "shards/train_manifest.json",
            "shards/val_manifest.json",
            "tokenizer_config.json"
        ]

        for file_path in metadata_files:
            src = self.dataset_root / file_path
            if src.exists():
                dst = version_dir / Path(file_path).name
                import shutil
                shutil.copy2(src, dst)

        # Save version info
        version_file = version_dir / "version.json"
        with open(version_file, 'w') as f:
            json.dump(asdict(version), f, indent=2)

    def commit_version(self, version: DatasetVersion):
        """Commit version to git"""
        try:
            repo = Repo(str(self.dataset_root))

            # Add registry and version files
            repo.index.add([
                str(self.registry_file),
                str(self.versions_dir / version.version)
            ])

            # Commit
            commit_msg = f"Dataset version {version.version}: {version.description}"
            repo.index.commit(commit_msg)

            logger.info("Committed version to git", version=version.version)

        except Exception as e:
            logger.warning("Failed to commit version to git", error=str(e))

    def get_version_info(self, version: Optional[str] = None) -> DatasetVersion:
        """Get information about a specific version"""
        if version is None:
            version = self.registry.current_version

        for v in self.registry.versions:
            if v.version == version:
                return v

        raise ValueError(f"Version {version} not found")

    def list_versions(self) -> List[str]:
        """List all available versions"""
        return [v.version for v in self.registry.versions]

    def compare_versions(self, version1: str, version2: str) -> Dict[str, Any]:
        """Compare two dataset versions"""
        v1 = self.get_version_info(version1)
        v2 = self.get_version_info(version2)

        comparison = {
            'version1': version1,
            'version2': version2,
            'statistics_diff': {},
            'quality_diff': {}
        }

        # Compare statistics
        for key in set(v1.statistics.keys()) | set(v2.statistics.keys()):
            val1 = v1.statistics.get(key, 0)
            val2 = v2.statistics.get(key, 0)
            if isinstance(val1, (int, float)) and isinstance(val2, (int, float)):
                comparison['statistics_diff'][key] = {
                    'v1': val1,
                    'v2': val2,
                    'diff': val2 - val1,
                    'pct_change': ((val2 - val1) / val1 * 100) if val1 != 0 else 0
                }

        # Compare quality metrics
        for key in set(v1.quality_metrics.keys()) | set(v2.quality_metrics.keys()):
            val1 = v1.quality_metrics.get(key, 0)
            val2 = v2.quality_metrics.get(key, 0)
            comparison['quality_diff'][key] = {
                'v1': val1,
                'v2': val2,
                'diff': val2 - val1
            }

        return comparison

    def export_version(self, version: str, output_dir: str):
        """Export a specific version for external use"""
        version_info = self.get_version_info(version)
        version_dir = self.versions_dir / version

        export_dir = Path(output_dir) / f"dataset-{version}"
        export_dir.mkdir(parents=True, exist_ok=True)

        # Copy metadata
        import shutil
        shutil.copytree(version_dir, export_dir / "metadata")

        # Create dataset info
        dataset_info = {
            'name': self.registry.name,
            'version': version,
            'description': self.registry.description,
            'created_at': version_info.created_at,
            'statistics': version_info.statistics,
            'quality_metrics': version_info.quality_metrics,
            'checksum': version_info.checksum
        }

        with open(export_dir / "dataset_info.json", 'w') as f:
            json.dump(dataset_info, f, indent=2)

        # Create README
        readme = f"""# {self.registry.name} v{version}

{self.registry.description}

## Version Information
- Created: {version_info.created_at}
- Description: {version_info.description}

## Statistics
{json.dumps(version_info.statistics, indent=2)}

## Quality Metrics
{json.dumps(version_info.quality_metrics, indent=2)}

## Checksum
{version_info.checksum}

## Usage
This dataset contains processed web crawl data ready for LLM training.
Use the metadata files to understand the dataset composition and quality.
"""
        with open(export_dir / "README.md", 'w') as f:
            f.write(readme)

        logger.info("Exported dataset version", version=version, output_dir=str(export_dir))
        return str(export_dir)

    def get_dataset_summary(self) -> Dict[str, Any]:
        """Get a summary of the current dataset"""
        if not self.registry.current_version:
            return {'status': 'empty'}

        current_version = self.get_version_info()

        # Load current statistics
        stats_file = self.dataset_root / "metadata" / "dataset_stats.csv"
        if stats_file.exists():
            df = pd.read_csv(stats_file)
            current_stats = {
                'total_documents': len(df),
                'total_tokens': df['token_estimate'].sum() if 'token_estimate' in df.columns else 0,
                'languages': df['language'].value_counts().to_dict() if 'language' in df.columns else {},
                'avg_quality': df['quality_score'].mean() if 'quality_score' in df.columns else 0
            }
        else:
            current_stats = {}

        return {
            'name': self.registry.name,
            'current_version': self.registry.current_version,
            'total_versions': len(self.registry.versions),
            'created_at': self.registry.created_at,
            'last_updated': self.registry.last_updated,
            'current_statistics': current_stats,
            'quality_metrics': current_version.quality_metrics,
            'description': current_version.description
        }


def main():
    """Main entry point"""
    import argparse

    parser = argparse.ArgumentParser(description='Dataset management and versioning')
    parser.add_argument('command', choices=['create', 'list', 'info', 'compare', 'export', 'summary'])
    parser.add_argument('--version', help='Version number')
    parser.add_argument('--description', help='Version description')
    parser.add_argument('--output-dir', default='exports', help='Output directory for export')
    parser.add_argument('--dataset-dir', default='dataset', help='Dataset directory')

    args = parser.parse_args()

    manager = DatasetManager(args.dataset_dir)

    if args.command == 'create':
        if not args.description:
            print("Description required for version creation")
            return

        # Mock statistics and metrics (would be calculated from actual data)
        stats = {'total_docs': 1000, 'total_tokens': 500000}
        quality = {'avg_quality': 0.85, 'language_coverage': 0.9}
        provenance = {'source': 'web_crawl', 'processing_pipeline': 'v1.0'}

        version = manager.create_version(args.description, stats, quality, provenance)
        print(f"Created version: {version}")

    elif args.command == 'list':
        versions = manager.list_versions()
        print("Available versions:")
        for v in versions:
            print(f"  {v}")

    elif args.command == 'info':
        version = args.version or manager.registry.current_version
        info = manager.get_version_info(version)
        print(f"Version {version}:")
        print(f"  Created: {info.created_at}")
        print(f"  Description: {info.description}")
        print(f"  Statistics: {info.statistics}")
        print(f"  Quality: {info.quality_metrics}")

    elif args.command == 'compare':
        if not args.version:
            print("Version to compare required")
            return
        comparison = manager.compare_versions(manager.registry.current_version, args.version)
        print(f"Comparing {comparison['version1']} vs {comparison['version2']}:")
        print("Statistics differences:")
        for key, diff in comparison['statistics_diff'].items():
            print(f"  {key}: {diff['v1']} -> {diff['v2']} ({diff['pct_change']:+.1f}%)")

    elif args.command == 'export':
        version = args.version or manager.registry.current_version
        output_dir = manager.export_version(version, args.output_dir)
        print(f"Exported version {version} to {output_dir}")

    elif args.command == 'summary':
        summary = manager.get_dataset_summary()
        print("Dataset Summary:")
        print(f"  Name: {summary['name']}")
        print(f"  Current Version: {summary['current_version']}")
        print(f"  Total Versions: {summary['total_versions']}")
        if 'current_statistics' in summary:
            stats = summary['current_statistics']
            print(f"  Total Documents: {stats.get('total_documents', 'N/A')}")
            print(f"  Total Tokens: {stats.get('total_tokens', 'N/A')}")


if __name__ == '__main__':
    main()
