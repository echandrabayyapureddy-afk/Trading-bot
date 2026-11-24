"""Development-window preflight. No market data, experiment or journal access."""
from dataclasses import dataclass, fields
from datetime import date, datetime
from pathlib import Path
import json

from config import (BotConfig, ConfigError, ResearchManifest, SealStatus, content_hash,
                    load_config, load_manifest, research_prerequisite_issues)
from data_fetcher import authorize_actual_research


@dataclass(frozen=True)
class DevelopmentWindow:
    snapshot_id: str
    snapshot_sha256: str
    manifest_sha256: str
    config_sha256: str
    start: date
    end: date
    authorization_at: datetime


@dataclass(frozen=True)
class SyntheticLoaderProbe:
    """A stand-in for the loader's metadata interface. Has no row-reading method."""
    snapshot_id: str
    snapshot_sha256: str

    def preview(self, window: DevelopmentWindow):
        return window


def preview_development_window(config: BotConfig, manifest: ResearchManifest, start: date, end: date,
                               loader: SyntheticLoaderProbe, *, expected_manifest_sha256: str,
                               authorization_at: datetime, verification_profiles: tuple):
    """Pass only an authorized half-open window to the synthetic loader."""
    authorize_actual_research(config, manifest, start, end, authorization_at=authorization_at,
                              expected_manifest_sha256=expected_manifest_sha256,
                              verification_profiles=verification_profiles)
    if type(loader) is not SyntheticLoaderProbe:
        raise ConfigError('synthetic metadata loader required')
    if (loader.snapshot_id, loader.snapshot_sha256) != (manifest.snapshot_id, manifest.snapshot_sha256):
        raise ConfigError('loader snapshot differs from sealed manifest')
    return loader.preview(DevelopmentWindow(manifest.snapshot_id, manifest.snapshot_sha256,
                          expected_manifest_sha256, content_hash(config), start, end, authorization_at))


def release_inventory(config, manifest):
    """Inventory of release metadata only. This cannot grant research authorization."""
    return {
        'real_research': 'BLOCKED',
        'manifest_status': manifest.status.value,
        'seal_required': manifest.status is not SealStatus.SEALED,
        'missing_manifest_fields': [f.name for f in fields(manifest)
                                    if getattr(manifest, f.name) in (None, ())],
        'missing_configuration': research_prerequisite_issues(config),
        'pinned_profile_count': len(config.execution.profile_sha256),
        'external_evidence_required': [
            'Independent manifest pin and approved seal, source and snapshot provenance',
            'Point-in-time corporate actions, identity history, dated constituents and benchmark',
            'Exchange session calendar, revisions and original availability timestamps',
            'Historically applicable broker, fee, slippage and adverse-execution profiles',
            'Current research approvals, revocations and actual authorization timestamp',
            'Owner-approved development-only study and range-restricted loader',
        ],
    }


if __name__ == '__main__':
    root = Path(__file__).resolve().parent
    print(json.dumps(release_inventory(load_config(root/'config.example.json'),
                                       load_manifest(root/'research_manifest.json')), indent=2))
