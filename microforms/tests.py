# -*- coding: utf-8 -*-
import unittest

import micromodels

from microforms.forms import model_form


class TestModel(micromodels.Model):
    title = micromodels.CharField()
    body = micromodels.CharField()
    images = micromodels.FieldCollectionField(micromodels.CharField())
    field4 = micromodels.CharField()
    field5 = micromodels.CharField()
    afield = micromodels.CharField()


class TestFormConversion(unittest.TestCase):
    def test_order_preservation(self):
        conv_form = model_form(TestModel)()
        self.assertEqual([x[0] for x in conv_form._unbound_fields],
             ['title', 'body', 'images', 'field4', 'field5', 'afield'])
