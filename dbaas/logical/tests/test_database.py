# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals
import mock
import logging
from unittest import skip
from django.test import TestCase
from django.db import IntegrityError
from drivers import base
from physical.tests import factory as physical_factory
from physical.models import DatabaseInfra
from logical.tests import factory
from ..models import Database


LOG = logging.getLogger(__name__)
ERROR_CLONE_WITHOUT_PERSISTENCE = \
    "Database does not have persistence cannot be cloned"
ERROR_CLONE_IN_QUARANTINE = "Database in quarantine cannot be cloned"
ERROR_CLONE_NOT_ALIVE = "Database is not alive and cannot be cloned"
ERROR_DELETE_PROTECTED = "Database {} is protected and cannot be deleted"
ERROR_DELETE_DEAD = "Database {} is not alive and cannot be deleted"


class FakeDriver(base.BaseDriver):

    def get_connection(self):
        return 'connection-url'


class DatabaseTestCase(TestCase):

    def setUp(self):
        self.instance = physical_factory.InstanceFactory()
        self.databaseinfra = self.instance.databaseinfra
        self.engine = FakeDriver(databaseinfra=self.databaseinfra)
        self.environment = physical_factory.EnvironmentFactory()

    def tearDown(self):
        self.engine = None

    def test_create_database(self):

        database = Database(name="blabla", databaseinfra=self.databaseinfra,
                            environment=self.environment)
        database.save()

        self.assertTrue(database.pk)

    def test_create_duplicate_database_error(self):

        database = Database(name="bleble", databaseinfra=self.databaseinfra,
                            environment=self.environment)

        database.save()

        self.assertTrue(database.pk)

        self.assertRaises(IntegrityError, Database(name="bleble",
                                                   databaseinfra=self.databaseinfra,
                                                   environment=self.environment).save)

    def test_slugify_database_name_with_spaces(self):

        database = factory.DatabaseFactory.build(name="w h a t",
                                                 databaseinfra=self.databaseinfra,
                                                 environment=self.environment)

        database.full_clean()
        database.save()
        self.assertTrue(database.id)
        self.assertEqual(database.name, 'w_h_a_t')

    def test_slugify_database_name_with_dots(self):
        database = factory.DatabaseFactory.build(name="w.h.e.r.e",
                                                 databaseinfra=self.databaseinfra,
                                                 environment=self.environment)

        database.full_clean()
        database.save()
        self.assertTrue(database.id)
        self.assertEqual(database.name, 'w_h_e_r_e')

    def test_cannot_edit_database_name(self):

        database = factory.DatabaseFactory(name="w h a t",
                                           databaseinfra=self.databaseinfra,
                                           environment=self.environment)

        self.assertTrue(database.id)

        database.name = "super3"

        self.assertRaises(AttributeError, database.save)

    @mock.patch.object(DatabaseInfra, 'get_info')
    def test_new_database_bypass_datainfra_info_cache(self, get_info):
        def side_effect_get_info(force_refresh=False):
            m = mock.Mock()
            if not force_refresh:
                m.get_database_status.return_value = None
                return m
            m.get_database_status.return_value = object()
            return m

        get_info.side_effect = side_effect_get_info
        database = factory.DatabaseFactory(name="db1cache",
                                           databaseinfra=self.databaseinfra,
                                           environment=self.environment)
        self.assertIsNotNone(database.database_status)
        self.assertEqual(
            [mock.call(), mock.call(force_refresh=True)], get_info.call_args_list)

    def test_can_update_nfsaas_used_disk_size(self):
        database = factory.DatabaseFactory()
        database.databaseinfra = self.databaseinfra

        nfsaas_host = physical_factory.NFSaaSHostAttr()
        nfsaas_host.host = self.instance.hostname
        nfsaas_host.save()

        old_used_size = nfsaas_host.nfsaas_used_size_kb
        nfsaas_host = database.update_host_disk_used_size(
            host_address=self.instance.address, used_size_kb=300
        )
        self.assertNotEqual(nfsaas_host.nfsaas_used_size_kb, old_used_size)
        self.assertEqual(nfsaas_host.nfsaas_used_size_kb, 300)

        old_used_size = nfsaas_host.nfsaas_used_size_kb
        nfsaas_host = database.update_host_disk_used_size(
            host_address=self.instance.address, used_size_kb=500
        )
        self.assertNotEqual(nfsaas_host.nfsaas_used_size_kb, old_used_size)
        self.assertEqual(nfsaas_host.nfsaas_used_size_kb, 500)

    def test_cannot_update_nfsaas_used_disk_size_host_not_nfsaas(self):
        database = factory.DatabaseFactory()
        database.databaseinfra = self.databaseinfra

        nfsaas_host = database.update_host_disk_used_size(
            host_address=self.instance.address, used_size_kb=300
        )
        self.assertIsNone(nfsaas_host)

    def test_can_clone(self):
        database = factory.DatabaseFactory()
        database.status = database.ALIVE

        can_be_cloned, error = database.can_be_cloned()
        self.assertTrue(can_be_cloned)
        self.assertIsNone(error)

    def test_cannot_clone_no_persistence(self):
        database = factory.DatabaseFactory()
        database.status = database.ALIVE
        database.plan.has_persistence = False

        can_be_cloned, error = database.can_be_cloned()
        self.assertFalse(can_be_cloned)
        self.assertEqual(error, ERROR_CLONE_WITHOUT_PERSISTENCE)

    def test_cannot_clone_in_quarantine(self):
        database = factory.DatabaseFactory()
        database.status = database.ALIVE
        database.is_in_quarantine = True

        can_be_cloned, error = database.can_be_cloned()
        self.assertFalse(can_be_cloned)
        self.assertEqual(error, ERROR_CLONE_IN_QUARANTINE)

    def test_cannot_clone_dead(self):
        database = factory.DatabaseFactory()
        database.status = database.DEAD
        database.database_status = None

        can_be_cloned, error = database.can_be_cloned()
        self.assertFalse(can_be_cloned)
        self.assertEqual(error, ERROR_CLONE_NOT_ALIVE)

    def test_can_delete(self):
        database = factory.DatabaseFactory()
        database.status = database.ALIVE

        can_be_deleted, error = database.can_be_deleted()
        self.assertTrue(can_be_deleted)
        self.assertIsNone(error)

    def test_cannot_delete_protected(self):
        database = factory.DatabaseFactory()
        database.status = database.ALIVE
        database.is_protected = True

        can_be_deleted, error = database.can_be_deleted()
        self.assertFalse(can_be_deleted)
        self.assertEqual(error, ERROR_DELETE_PROTECTED.format(database.name))

    def test_can_delete_protected_in_quarantine(self):
        database = factory.DatabaseFactory()
        database.status = database.ALIVE
        database.is_protected = True
        database.is_in_quarantine = True

        can_be_deleted, error = database.can_be_deleted()
        self.assertTrue(can_be_deleted)
        self.assertIsNone(error)

    def test_can_delete_in_quarantine(self):
        database = factory.DatabaseFactory()
        database.status = database.ALIVE
        database.is_in_quarantine = True

        can_be_deleted, error = database.can_be_deleted()
        self.assertTrue(can_be_deleted)
        self.assertIsNone(error)

    def test_cannot_delete_dead(self):
        database = factory.DatabaseFactory()
        database.status = database.DEAD

        can_be_deleted, error = database.can_be_deleted()
        self.assertFalse(can_be_deleted)
        self.assertEqual(error, ERROR_DELETE_DEAD.format(database.name))

    '''

    @mock.patch.object(clone_database, 'delay')
    def test_database_clone(self, delay):

        database = Database(name="morpheus", databaseinfra=self.databaseinfra)

        database.save()

        self.assertTrue(database.pk)

        clone_name = "morpheus_clone"
        Database.clone(database, clone_name, None)

        clone_database = Database.objects.get(name=clone_name)

        self.assertTrue(clone_database.pk)
        self.assertEqual(clone_database.name, clone_name)
        self.assertEqual(clone_database.project, database.project)
        self.assertEqual(clone_database.team, database.team)

        credential = clone_database.credentials.all()[0]

        self.assertEqual(credential.user, "u_morpheus_clone")

    @mock.patch.object(clone_database, 'delay')
    def test_database_clone_with_white_space(self, delay):
        """Tests that a clone database created with white spaces passes the test"""

        database = Database(name="trinity", databaseinfra=self.databaseinfra)

        database.save()

        self.assertTrue(database.pk)

        clone_name = "trinity clone"
        Database.clone(database, clone_name, None)

        clone_database = Database.objects.get(name="trinity_clone")

        self.assertTrue(clone_database.pk)
        self.assertEqual(clone_database.name, "trinity_clone")
        self.assertEqual(clone_database.project, database.project)
        self.assertEqual(clone_database.team, database.team)

        credential = clone_database.credentials.all()[0]

        self.assertEqual(credential.user, "u_trinity_clone")

    '''
