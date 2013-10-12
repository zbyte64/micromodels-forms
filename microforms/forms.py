"""
Tools for generating forms based on micromodels.
"""
from collections import OrderedDict

from wtforms import fields as f
from wtforms import Form
from wtforms import validators
from wtforms.compat import iteritems

from .fields import URIField, URIFileField


__all__ = (
    'model_fields', 'model_form',
    'MicroModelConverterBase', 'MicroModelConverter',
    'MicromodelForm',
)


class MicroModelConverterBase(object):
    def __init__(self, converters):
        self.converters = converters

    def convert(self, model, field, field_args):
        kwargs = {
            'label': field.verbose_name,
            'description': field.help_text,
            'validators': [],
            'filters': [],
            'default': field.default,
        }
        if field_args:
            kwargs.update(field_args)

        if not field.required:
            kwargs['validators'].append(validators.Optional())
        #if field.max_length is not None and field.max_length > 0:
        #    kwargs['validators'].append(validators.Length(max=field.max_length))

        ftype = type(field).__name__
        #if field.choices:
        #    kwargs['choices'] = field.choices
        #    return f.SelectField(**kwargs)
        if ftype in self.converters:
            return self.converters[ftype](model, field, kwargs)
        else:
            converter = getattr(self, 'conv_%s' % ftype, None)
            if converter is not None:
                return converter(model, field, kwargs)


class MicroModelConverter(MicroModelConverterBase):
    DEFAULT_SIMPLE_CONVERSIONS = {
        f.IntegerField: ['AutoField', 'IntegerField', 'SmallIntegerField', 'PositiveIntegerField', 'PositiveSmallIntegerField'],
        f.DecimalField: ['DecimalField', 'FloatField'],
        f.FileField: ['FileField', 'FilePathField', 'ImageField'],
        f.DateTimeField: ['DateTimeField'],
        f.DateField: ['DateField'],
        f.BooleanField: ['BooleanField'],
        f.TextField: ['CharField', 'PhoneNumberField', 'SlugField'],
        f.TextAreaField: ['TextField', 'XMLField', 'JSONField'],
        URIFileField: ['URIFileField'],
        URIField: ['URIField', 'URLField'],
    }

    def __init__(self, extra_converters=None, simple_conversions=None):
        converters = {}
        if simple_conversions is None:
            simple_conversions = self.DEFAULT_SIMPLE_CONVERSIONS
        for field_type, django_fields in iteritems(simple_conversions):
            converter = self.make_simple_converter(field_type)
            for name in django_fields:
                converters[name] = converter

        if extra_converters:
            converters.update(extra_converters)
        super(MicroModelConverter, self).__init__(converters)

    def make_simple_converter(self, field_type):
        def _converter(model, field, kwargs):
            return field_type(**kwargs)
        return _converter

    def conv_TimeField(self, model, field, kwargs):
        def time_only(obj):
            try:
                return obj.time()
            except AttributeError:
                return obj
        kwargs['filters'].append(time_only)
        return f.DateTimeField(format='%H:%M:%S', **kwargs)

    def conv_EmailField(self, model, field, kwargs):
        kwargs['validators'].append(validators.email())
        return f.TextField(**kwargs)

    def conv_IPAddressField(self, model, field, kwargs):
        kwargs['validators'].append(validators.ip_address())
        return f.TextField(**kwargs)

    def conv_URLField(self, model, field, kwargs):
        kwargs['validators'].append(validators.url())
        return f.TextField(**kwargs)

    def conv_NullBooleanField(self, model, field, kwargs):
        def coerce_nullbool(value):
            d = {'None': None, None: None, 'True': True, 'False': False}
            if value in d:
                return d[value]
            else:
                return bool(int(value))

        choices = ((None, 'Unknown'), (True, 'Yes'), (False, 'No'))
        return f.SelectField(choices=choices, coerce=coerce_nullbool, **kwargs)

    def conv_ModelField(self, model, field, kwargs):
        form = model_form(field._wrapped_class)
        return f.FormField(form, default=field._wrapped_class)

    def conv_ModelCollectionField(self, model, field, kwargs):
        form = model_form(field._wrapped_class)
        return f.FieldList(f.FormField(form, default=field._wrapped_class))

    def conv_FieldCollectionField(self, model, field, kwargs):
        form_field = self.convert(model, field._instance, {})
        return f.FieldList(form_field)


def model_fields(model, only=None, exclude=None, field_args=None, converter=None):
    """
    Generate a dictionary of fields for a given micromodel.

    See `model_form` docstring for description of parameters.
    """
    converter = converter or MicroModelConverter()
    field_args = field_args or {}

    model_fields = ((key, f) for key, f in model._clsfields.items())
    if only:
        model_fields = (x for x in model_fields if x[0] in only)
    elif exclude:
        model_fields = (x for x in model_fields if x[0] not in exclude)

    field_dict = OrderedDict()
    for name, model_field in model_fields:
        field = converter.convert(model, model_field, field_args.get(name))
        if field is not None:
            field_dict[name] = field

    return field_dict


def model_form(model, base_class=Form, only=None, exclude=None, field_args=None, converter=None):
    """
    Create a wtforms Form for a given micromodel class::

        from wtforms.ext.django.orm import model_form
        from myproject.myapp.models import User
        UserForm = model_form(User)

    :param model:
        A micromodel class
    :param base_class:
        Base form class to extend from. Must be a ``wtforms.Form`` subclass.
    :param only:
        An optional iterable with the property names that should be included in
        the form. Only these properties will have fields.
    :param exclude:
        An optional iterable with the property names that should be excluded
        from the form. All other properties will have fields.
    :param field_args:
        An optional dictionary of field names mapping to keyword arguments used
        to construct each field object.
    :param converter:
        A converter to generate the fields based on the model properties. If
        not set, ``ModelConverter`` is used.
    """
    field_dict = model_fields(model, only, exclude, field_args, converter)
    return type(model.__name__ + 'Form', (base_class, ), field_dict)


class MicromodelFormOptions(object):
    def __init__(self, options=None):
        self.model = getattr(options, 'model', None)
        self.fields = getattr(options, 'fields', None)
        self.exclude = getattr(options, 'exclude', None)
        self.widgets = getattr(options, 'widgets', None)
        self.converter = getattr(options, 'converter', None)
        self.field_args = getattr(options, 'field_args', None)


class MicromodelFormMeta(type(Form)):
    def __init__(cls, name, bases, attrs):
        super(MicromodelFormMeta, cls).__init__(name, bases, attrs)
        opts = cls._meta = MicromodelFormOptions(getattr(cls, 'Meta', None))
        if opts.model:
            fields = model_fields(opts.model, only=opts.fields,
                exclude=opts.exclude, field_args=opts.field_args,
                converter=opts.converter)
            for key, attr in fields.items():
                setattr(cls, key, attr)


class MicromodelForm(Form):
    __metaclass__ = MicromodelFormMeta

    class Meta:
        pass

