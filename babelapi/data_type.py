"""
Defines data types for Babel.

The data types defined here should include all data types we expect to support
across all serialization formats. For example, if we were just supporting JSON,
we would only have a Number type since all numbers in Javascript are doubles.
But, we may want to eventually support Protobuf, which has primitives closer
to those in C. This is why Int32 and UInt32 are differentiated, though it has
the added benefit that the user is able to reason between signed vs. unsigned.
"""

from abc import ABCMeta, abstractmethod
from collections import OrderedDict
import copy
import datetime
import numbers
import re
import types

class DataType(object):
    """
    Abstract class representing a data type.

    When extending, use a class name that matches exactly the name you will
    want to use when referencing in a template.
    """

    __metaclass__ = ABCMeta

    @property
    def name(self):
        """Returns an easy to read name for the type."""
        return self.__class__.__name__

    @abstractmethod
    def check(self, val):
        """
        Checks if val is a valid Python representation for this type. Either
        raises a ValueError or returns None. Return value should be ignored.
        """
        pass

    def __repr__(self):
        return self.name

class PrimitiveType(DataType):
    pass

class Null(PrimitiveType):
    def check(self, val):
        if val is not None:
            raise ValueError('%r is not a valid null type' % val)

class Symbol(PrimitiveType):
    def __init__(self, symbol_name):
        self.symbol_name = symbol_name
    def check(self, val):
        # FIXME: Uncertain whether val should be string or some Id class.
        if val != self.symbol_name:
            raise ValueError('val %r is not symbol %r' % (val, self.symbol_name))

class Binary(PrimitiveType):
    def check(self, val):
        if not isinstance(val, str):
            raise ValueError('%r is not valid binary (Python str)' % val)

    @property
    def has_example(self, label):
        return False

    @property
    def get_example(self, label):
        return None

class _BoundedInteger(PrimitiveType):
    """
    When extending, specify 'minimum' and 'maximum' as class variables.
    """
    def __init__(self, min_value=None, max_value=None):
        """
        A more restrictive minimum or maximum value can be specified than the
        range inherent to the defined type.
        """
        if min_value is not None:
            if min_value >= self.minimum:
                self.minimum = min_value
            else:
                raise ValueError('min_value cannot be less than the minimum '
                                 'value for this type (%s < %s)'
                                 % (min_value, self.minimum))
        if max_value is not None:
            if max_value <= self.maximum:
                self.maximum = max_value
            else:
                raise ValueError('max_value cannot be greater than the maximum '
                                 'value for this type (%s < %s)'
                                 % (max_value, self.maximum))

    def check(self, val):
        if not isinstance(val, numbers.Integral):
            raise ValueError('%r is not a valid integer type' % val)
        elif not (self.minimum <= val <= self.maximum):
            raise ValueError('%s is not within range [%r, %r]'
                             % (val, self.minimum, self.maximum))

    def __repr__(self):
        return '%s()' % self.name

class Int32(_BoundedInteger):
    minimum = -2**31
    maximum = 2**31 - 1

class UInt32(_BoundedInteger):
    minimum = 0
    maximum = 2**32 - 1

class Int64(_BoundedInteger):
    minimum = -2**63
    maximum = 2**63 - 1

class UInt64(_BoundedInteger):
    minimum = 0
    maximum = 2**64 - 1

class BigInt(PrimitiveType):
    def check(self, val):
        if not isinstance(val, numbers.Integral):
            raise ValueError('%r is not a valid integer')

class Float32(PrimitiveType):
    # TODO: Decide how to enforce a 32-bit float
    def check(self, val):
        if not isinstance(val, numbers.Real):
            raise ValueError('%r is not a valid float' % val)

class Float64(PrimitiveType):
    def check(self, val):
        if not isinstance(val, numbers.Real):
            raise ValueError('%r is not a valid double' % val)

class Boolean(PrimitiveType):
    def check(self, val):
        if not isinstance(val, bool):
            raise ValueError('%r is not a valid boolean' % val)

class String(PrimitiveType):
    def __init__(self, min_length=None, max_length=None, pattern=None):
        if min_length is not None:
            assert isinstance(min_length, numbers.Integral), (
                'min_length must be an integral number'
            )
            assert min_length >= 0, 'min_length must be >= 0'
        if max_length is not None:
            assert isinstance(max_length, numbers.Integral), (
                'max_length must be an integral number'
            )
            assert max_length > 0, 'max_length must be > 0'
        if min_length and max_length:
            assert max_length >= min_length, 'max_length must be >= min_length'

        self.min_length = min_length
        self.max_length = max_length
        self.pattern = pattern
        self.pattern_re = None

        if pattern:
            try:
                self.pattern_re = re.compile(pattern)
            except re.error as e:
                raise ValueError('Regex {!r} failed: {}'.format(pattern, e.args[0]))

    def check(self, val):
        if not isinstance(val, types.StringTypes):
            raise ValueError('%r is not a valid string' % val)
        elif self.max_length is not None and len(val) > self.max_length:
            raise ValueError('%r has more than %s characters'
                             % (val, self.max_length))
        elif self.min_length is not None and len(val) < self.min_length:
            raise ValueError('%r has fewer than %s characters'
                             % (val, self.min_length))
        elif self.pattern and not self.pattern_re.match(val):
            raise ValueError('%r did not match pattern %r'
                             % (val, self.pattern))

class Timestamp(PrimitiveType):
    """Should support any timestamp format, not just the Dropbox format."""

    def __init__(self, format):
        self.format = format

    def check(self, val):
        if not isinstance(val, types.StringTypes):
            raise ValueError('Timestamp must be specified as a str')

        # Raises a ValueError if val is the incorrect format
        datetime.datetime.strptime(val, self.format)

class List(DataType):
    """Assumes list contents are homogeneous with respect to types."""

    def __init__(self, data_type, min_items=None, max_items=None):
        self.data_type = data_type

        if min_items is not None:
            assert min_items >= 0, 'min_items must be >= 0'
        if max_items is not None:
            assert max_items > 0, 'max_items must be > 0'
        if min_items and max_items:
            assert max_items >= min_items, 'max_length must be >= min_length'

        self.min_items = min_items
        self.max_items = max_items

    def check(self, val):
        if not isinstance(val, types.ListType):
            raise ValueError('%r is not a valid list' % val)
        elif self.max_items is not None and len(val) > self.max_items:
            raise ValueError('%r has more than %s items'
                             % (val, self.max_items))
        elif self.min_items is not None and len(val) < self.min_items:
            raise ValueError('%r has fewer than %s items'
                             % (val, self.min_items))
        for item in val:
            self.data_type.check(item)

    def has_example(self, label):
        if isinstance(self.data_type, CompositeType):
            return self.data_type.has_example(label)
        else:
            return False

    def get_example(self, label):
        if isinstance(self.data_type, CompositeType):
            return self.data_type.get_example(label)
        else:
            return None

class Field(object):
    """
    Represents a field in a composite type.
    """

    def __init__(self,
                 name,
                 data_type,
                 doc,
                 nullable=False,
                 optional=False,
                 deprecated=False):
        """
        Creates a new Field.

        :param str name: Name of the field.
        :param Type data_type: The type of variable for of this field.
        :param str doc: Documentation for the field.
        :param bool nullable: Whether the field can be null.
        :param bool optional: Whether the field can be absent.
        :param bool deprecated: Whether the field is deprecated.
        """
        self.name = name
        self.data_type = data_type
        self.doc = doc
        self.nullable = nullable
        self.optional = optional
        self.deprecated = deprecated
        self.has_default = False
        self._default = None

    def set_default(self, default):
        self.has_default = True
        self._default = default

    @property
    def default(self):
        if not self.has_default:
            raise Exception('Type has no default')
        else:
            return self._default

    def check(self, val):
        if val is None:
            if self.nullable:
                return None
            else:
                raise ValueError('val is None but field is not nullable')
        else:
            return self.data_type.check(val)

    def __repr__(self):
        return 'Field(%r, %r, %r, %r)' % (self.name,
                                          self.data_type,
                                          self.nullable,
                                          self.optional)

class SymbolField(object):
    symbol = True
    def __init__(self, name, doc):
        """
        Creates a new SymbolField.

        :param str name: Name of the field.
        :param str doc: Documentation for the field.
        """
        self.name = name
        self.data_type = Symbol(name)
        self.doc = doc

    def check(self, val):
        if val != self.name:
            raise ValueError('val %r is not symbol %r' % (val, self.name))

    def __repr__(self):
        return 'SymbolField(%r)' % self.name

class CompositeType(DataType):
    """
    Composite types are any data type which can be constructed using primitive
    data types and other composite types.
    """

    DEFAULT_EXAMPLE_LABEL = 'default'

    def __init__(self, name, doc, fields, super_type=None):
        """
        Creates a CompositeType.

        Fields are specified as a list so that order is preserved for display
        purposes only. (Might be used for certain serialization formats...)

        :param str name: Name of type.
        :param str doc: Description of type.
        :param list(Field) fields: Ordered list of fields for type.
        :param dict example: An example of the type as a JSON-compatible dict.
        :param CompositeType super_type: If this should subtype another.
        """
        self._name = name
        self.doc = doc
        self.fields = fields
        self.super_type = super_type
        self.examples = {}

    @property
    def all_fields(self):
        """
        Returns an iterator of all fields. Required fields before optional
        fields. Super type fields before type fields.
        """
        return self.all_required_fields + self.all_optional_fields

    def _filter_fields(self, filter_function):
        """
        Utility to iterate through all fields (super types first) of a type.

        :param filter: A function that takes in a Field object. If it returns
            True, the field is part of the generated output. If False, it is
            omitted.
        """
        fields = []
        if self.super_type:
            fields.extend(self.super_type._filter_fields(filter_function))
        fields.extend(filter(filter_function, self.fields))
        return fields

    @property
    def all_required_fields(self):
        """
        Returns an iterator that traverses required fields in all super types
        first, and then for this type.
        """
        return self._filter_fields(lambda f: (isinstance(f, SymbolField)
                                              or not f.optional))

    @property
    def all_optional_fields(self):
        """
        Returns an iterator that traverses optional fields in all super types
        first, and then for this type.
        """
        return self._filter_fields(lambda f: (not isinstance(f, SymbolField)
                                              and f.optional))

    @property
    def name(self):
        return self._name

    @abstractmethod
    def get_example(self, label, example):
        pass

    @abstractmethod
    def add_example(self, label, text, example):
        pass

    def copy(self):
        return copy.deepcopy(self)

    def prepend_field(self, field):
        self.fields.insert(0, field)

class OrderedExample(OrderedDict):

    def __init__(self, *args, **kwargs):
        super(OrderedExample, self).__init__(*args, **kwargs)
        self.text = None

class Struct(CompositeType):
    """
    Defines a product type: Composed of other primitive and/or struct types.
    """

    composite_type = 'struct'

    def __init__(self, name, doc, fields, super_type=None, coverage_names=None):
        super(Struct, self).__init__(name, doc, fields, super_type=super_type)
        self.coverage_names = coverage_names
        self.coverage = []

    def has_coverage(self):
        return bool(self.coverage_names)

    def resolve_coverage(self, env):
        """
        Struct is defined before types that it covers are defined. So use an
        env to resolve the name of those data types into data type objects.
        """
        for coverage_name in self.coverage_names:
            if coverage_name in env:
                data_type = env[coverage_name]
                if data_type.super_type is None:
                    raise ValueError('All coverage must be subtypes of %r'
                                     % self.name)
                if data_type.super_type != self:
                    raise ValueError('All coverage must subtype %r not %r'
                                     % (self.name, data_type.super_type.name))
                self.coverage.append(data_type)
            else:
                raise KeyError('No data type named %s' % coverage_name)

    def check(self, val):
        # Enforce the existence of all fields
        if not isinstance(val, dict):
            raise ValueError('val must be a dict')

        for field in self.fields:
            if field.name in val:
                field.check(val[field.name])
            else:
                raise ValueError('Field %r is unspecified' % field.name)

    def add_example(self, label, text, example):
        """
        Add a plausible example of the contents of this type. The example is
        validated against the type definition.

        :param str label: A label for the example.
        :param dict example: An example of the type represented as a dict of a
            subset of Python primitives (str, unicode, list, int/long, float).
        """
        if label in example:
            raise ValueError('Example label %s already specified' % label)

        ordered_example = OrderedExample()
        ordered_example.text = text

        # Check for examples with keys that don't belong
        extra_fields = set(example.keys()) - set([f.name for f in self.all_fields])
        if extra_fields:
            raise KeyError('Example for %r has invalid fields %r'
                           % (self.name, extra_fields))

        for field in self.all_fields:
            if field.name in example:
                if isinstance(field.data_type, CompositeType):
                    # An example that specifies the key as null is okay if the
                    # field permits it.
                    if field.nullable and example[field.name] is None:
                        ordered_example[field.name] = None
                    else:
                        raise KeyError('Field %r should not be specified since '
                                       'it is a composite type declaration.'
                                       % field.name)
                elif isinstance(field.data_type, List):
                    if isinstance(field.data_type.data_type, CompositeType):
                        raise KeyError('Field %r should not be specified '
                                       'since it is a list of composite '
                                       'types.' % field.name)
                    else:
                        field.check(example[field.name])
                        ordered_example[field.name] = example[field.name]
                else:
                    field.check(example[field.name])
                    ordered_example[field.name] = example[field.name]
            elif not isinstance(field.data_type, (CompositeType, List)) and not field.optional:
                raise KeyError('Missing field %r in example' % field.name)
        self.examples[label] = ordered_example

    def has_example(self, label):
        return label in self.examples

    def get_example(self, label):
        example = self.examples.get(label)
        if example is None:
            return None
        else:
            example_copy = copy.copy(example)
            for field in self.all_fields:
                if field.name in example_copy:
                    # Only valid when the field has been set to null in the
                    # example.
                    continue
                elif isinstance(field.data_type, CompositeType):
                    if field.data_type.has_example(label):
                        example_copy[field.name] = field.data_type.get_example(label)
                    elif field.data_type.has_example(self.DEFAULT_EXAMPLE_LABEL):
                        example_copy[field.name] = field.data_type.get_example(
                            self.DEFAULT_EXAMPLE_LABEL,
                        )
                    else:
                        raise Exception('No example with label %r for subtype '
                                        '%r' % (label, field.data_type.name))
                elif (isinstance(field.data_type, List) and
                          isinstance(field.data_type.data_type, CompositeType)):
                    example_copy[field.name] = [field.data_type.data_type.get_example(label)]
            return example_copy

    def __repr__(self):
        return 'Struct(%r, %r)' % (self.name, self.fields)

class Union(CompositeType):
    """Defines a tagged union. Fields are variants."""

    composite_type = 'union'

    def __init__(self, name, doc, fields, super_type=None, catch_all_field=None):
        super(Union, self).__init__(name, doc, fields, super_type=super_type)
        self.catch_all_field = catch_all_field

    def check(self, val):
        if isinstance(val, dict):
            assert isinstance(val, dict), 'val must be a dict'
            assert len(val.keys()) == 1, 'Union should only have 1 tag specified'

            tag = val.keys()[0]
            for field in self.fields:
                if tag == field.name:
                    return field.check(val[tag])
            else:
                raise KeyError('Tag %r is not valid variant' % tag)
        elif isinstance(val, str):
            for field in self.fields:
                if val == field.name:
                    return None
            else:
                raise KeyError('Tag %r is not a valid variant' % val)
        else:
            raise ValueError('val must be a dict or str')

    def has_example(self, label):
        for field in self.fields:
            if (isinstance(field, Field)
                and isinstance(field.data_type, CompositeType)
                and field.data_type.has_example(label)):

                return True
        else:
            for field in self.fields:
                if isinstance(field, SymbolField) and field.name == label:
                    return True

            return False
        return False

    def get_example(self, label):
        for field in self.fields:
            if (isinstance(field, Field)
                and isinstance(field.data_type, CompositeType)
                and field.data_type.has_example(label)):

                return {field.name: field.data_type.get_example(label)}
        else:
            # Fallback to checking for direct symbols
            for field in self.fields:
                if isinstance(field, SymbolField) and field.name == label:
                    return field.name
            else:
                return None

    def add_example(self, label, example):
        raise NotImplemented

    def unique_field_data_types(self):
        """
        Checks if all variants have different data types.

        If so, the selected variant can be determined just by the data type of
        the value without needing a field name / tag. In some languages, this
        lets us make a shortcut
        """
        data_type_names = set()
        for field in self.fields:
            if not isinstance(field, SymbolField):
                if field.data_type.name in data_type_names:
                    return False
                else:
                    data_type_names.add(field.data_type.name)
        else:
            return True

    def __repr__(self):
        return 'Union(%r, %r)' % (self.name, self.fields)

Empty = Struct('Empty', None, [])

def is_binary_type(data_type):
    return isinstance(data_type, Binary)
def is_composite_type(data_type):
    return isinstance(data_type, CompositeType)
def is_list_type(data_type):
    return isinstance(data_type, List)
def is_null_type(data_type):
    return isinstance(data_type, Null)
def is_struct_type(data_type):
    return isinstance(data_type, Struct)
def is_timestamp_type(data_type):
    return isinstance(data_type, Timestamp)
def is_union_type(data_type):
    return isinstance(data_type, Union)
