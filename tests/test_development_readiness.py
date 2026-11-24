"""No market rows are needed to test the authorization/loader boundary."""
from dataclasses import replace
from datetime import timedelta
from unittest import TestCase
from unittest.mock import patch

from config import BotConfig, ConfigError, ResearchManifest, content_hash
from development_readiness import (DevelopmentWindow, SyntheticLoaderProbe,
                                  preview_development_window, release_inventory)
from test_config import ready_config, research_profiles, sealed_manifest


class DevelopmentReadinessTests(TestCase):
    def setUp(self):
        self.config = ready_config()
        self.manifest = sealed_manifest(self.config)
        self.profiles = research_profiles()
        self.now = self.manifest.sealed_at + timedelta(days=7)
        self.loader = SyntheticLoaderProbe(self.manifest.snapshot_id, self.manifest.snapshot_sha256)
        self.args = dict(config=self.config, manifest=self.manifest, start=self.manifest.development_start,
                         end=self.manifest.development_end, expected_manifest_sha256=content_hash(self.manifest),
                         loader=self.loader, authorization_at=self.now, verification_profiles=self.profiles)

    def rejected(self, reason, **changes):
        with patch.object(SyntheticLoaderProbe, 'preview', autospec=True) as receive:
            with self.assertRaisesRegex(ConfigError, reason):
                preview_development_window(**(self.args | changes))
            receive.assert_not_called()

    def test_exclusive_boundary_delivered_once(self):
        m = self.manifest
        original = SyntheticLoaderProbe.preview
        with patch.object(SyntheticLoaderProbe, 'preview', autospec=True, side_effect=original) as receive:
            received = preview_development_window(**self.args)
            expected = DevelopmentWindow(m.snapshot_id, m.snapshot_sha256, content_hash(m), content_hash(self.config),
                                         m.development_start, m.holdout_start, self.now)
            receive.assert_called_once_with(self.loader, expected)
            self.assertEqual(received, expected)

    def test_unsealed_and_pin(self):
        m = ResearchManifest()
        self.rejected('UNSEALED', manifest=m, expected_manifest_sha256=content_hash(m))
        self.rejected('manifest hash mismatch', expected_manifest_sha256='0'*64)

    def test_snapshot_and_config(self):
        for loader in (replace(self.loader, snapshot_id='other'), replace(self.loader, snapshot_sha256='0'*64)):
            self.rejected('loader snapshot', loader=loader)
        self.rejected('configuration differs', config=replace(self.config, config_version='0.4.0'))

    def test_current_revocation_and_missing_profiles(self):
        first, *others = self.profiles
        revoked = replace(first, approval=replace(first.approval, revoked_at=self.now))
        self.rejected('revoked', verification_profiles=(revoked, *others))
        self.rejected('four research', verification_profiles=tuple(others))
        self.rejected('explicit aware', authorization_at=None)

    def test_crossing_and_holdout_only(self):
        boundary = self.manifest.holdout_start
        self.rejected('holdout access denied', end=boundary+timedelta(days=1))
        self.rejected('holdout access denied', start=boundary, end=boundary+timedelta(days=1))

    def test_full_snapshot_provider_incompatible(self):
        from data_fetcher import UnverifiedProvider
        with patch.object(UnverifiedProvider, 'fetch') as fetch:
            self.rejected('synthetic metadata loader required', loader=UnverifiedProvider())
            fetch.assert_not_called()

    def test_template_inventory(self):
        report = release_inventory(BotConfig(), ResearchManifest())
        self.assertEqual(report['real_research'], 'BLOCKED')
        self.assertTrue(report['seal_required'])
        self.assertIn('holdout_start', report['missing_manifest_fields'])
        self.assertIn('data.availability_verified', report['missing_configuration'])
        self.assertEqual(report['pinned_profile_count'], 0)
