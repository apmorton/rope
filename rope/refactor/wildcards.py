from rope.base import ast, evaluate, builtins, pyobjects
from rope.refactor import patchedast, occurrences


class Wildcard(object):

    def get_name(self):
        """Return the name of this wildcard"""

    def matches(self, suspect, arg):
        """Return `True` if `suspect` matches this wildcard"""


class Suspect(object):

    def __init__(self, pymodule, node, name):
        self.name = name
        self.pymodule = pymodule
        self.node = node


class DefaultWildcard(object):
    """The default restructuring wildcard

    The argument passed to this wildcard is in the
    ``key1=value1,key2=value2,...`` format.  Possible keys are:

    * name - for checking the reference
    * type - for checking the type
    * object - for checking the object
    * instance - for checking types but similar to builtin isinstance
    * exact - matching only occurrences with the same name as the wildcard

    """

    def __init__(self, project):
        self.project = project

    def get_name(self):
        return 'default'

    def matches(self, suspect, arg=''):
        args = parse_arg(arg)

        node = suspect.node
        if args.get('exact'):
            if not isinstance(node, ast.Name) or not node.id == suspect.name:
                return False
        else:
            if not isinstance(node, ast.expr):
                return False
        kind = None
        expected = None
        for check in ['name', 'object', 'type', 'instance']:
            if check in args:
                kind = check
                expected = args[check]
        if expected is not None:
            return _CheckObject(self.project, expected, kind)(suspect.pymodule,
                                                              suspect.node)
        return True


def parse_arg(arg):
    result = {}
    tokens = arg.split(',')
    for token in tokens:
        if '=' in token:
            parts = token.split('=', 1)
            result[parts[0].strip()] = parts[1].strip()
        else:
            result[token.strip()] = True
    return result


class _CheckObject(object):

    def __init__(self, project, expected, kind='object'):
        self.project = project
        self.kind = kind
        self.expected = self._evaluate(expected)

    def __call__(self, pymodule, node):
        pyname = self._evaluate_node(pymodule, node)
        if self.expected is None or pyname is None:
            return False
        if self.kind == 'name':
            return self._same_pyname(self.expected, pyname)
        else:
            pyobject = pyname.get_object()
            if self.kind == 'object':
                objects = [pyobject]
            if self.kind == 'type':
                objects = [pyobject.get_type()]
            if self.kind == 'instance':
                objects = [pyobject]
                objects.extend(self._get_super_classes(pyobject))
                objects.extend(self._get_super_classes(pyobject.get_type()))
            for pyobject in objects:
                if self._same_pyobject(self.expected.get_object(), pyobject):
                    return True
            return False

    def _get_super_classes(self, pyobject):
        result = []
        if isinstance(pyobject, pyobjects.AbstractClass):
            for superclass in pyobject.get_superclasses():
                result.append(superclass)
                result.extend(self._get_super_classes(superclass))
        return result

    def _same_pyobject(self, expected, pyobject):
        return expected == pyobject

    def _same_pyname(self, expected, pyname):
        return occurrences.same_pyname(expected, pyname)

    def _split_name(self, name):
        parts = name.split('.')
        expression, kind = parts[0], parts[-1]
        if len(parts) == 1:
            kind = 'name'
        return expression, kind

    def _evaluate_node(self, pymodule, node):
        scope = pymodule.get_scope().get_inner_scope_for_line(node.lineno)
        expression = node
        if isinstance(expression, ast.Name) and \
           isinstance(expression.ctx, ast.Store):
            start, end = patchedast.node_region(expression)
            text = pymodule.source_code[start:end]
            return evaluate.get_string_result(scope, text)
        else:
            return evaluate.get_statement_result(scope, expression)

    def _evaluate(self, code):
        attributes = code.split('.')
        pyname = None
        if attributes[0] in ('__builtin__', '__builtins__'):
            class _BuiltinsStub(object):
                def get_attribute(self, name):
                    return builtins.builtins[name]
                def __getitem__(self, name):
                    return builtins.builtins[name]
                def __contains__(self, name):
                    return name in builtins.builtins
            pyobject = _BuiltinsStub()
        else:
            pyobject = self.project.pycore.get_module(attributes[0])
        for attribute in attributes[1:]:
            pyname = pyobject[attribute]
            if pyname is None:
                return None
            pyobject = pyname.get_object()
        return pyname