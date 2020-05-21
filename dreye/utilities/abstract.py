"""
"""


from abc import ABC, abstractmethod

from dreye.err import DreyeError


class _AbstractArray(ABC):
    """
    Abstract Sequence
    """

    @abstractmethod
    def to_dict(self):
        pass

    @abstractmethod
    def from_dict(self):
        pass


class CallableList(list):
    """Works the same way as a native python list except that it has a
    __call__ method that is applied to each element of the list.
    """

    def __init__(self, iterable, container_class=None):
        super().__init__(iterable)
        self._container_class = container_class

    def __call__(self, *args, iter_kwargs=None, **kwargs):
        container = [
            ele(*args, **kwargs)
            if iter_kwargs is None
            else ele(*args, **kwargs, **iter_kwargs[index])
            for index, ele in enumerate(self)
        ]
        if self._container_class is None:
            return CallableList(
                container,
                self._container_class
            )
        elif self._container_class._are_instances(container):
            return self._container_class(container)
        else:
            return CallableList(
                container,
                self._container_class
            )


class _AbstractContainer(ABC):

    _init_keys = []

    def __init__(self, container):
        self._container = self._check_list(container)
        self._init_attrs()

    def _init_attrs(self):
        for key in self._init_keys:
            setattr(self, key, None)

    @property
    @abstractmethod
    def _allowed_instances(self):
        pass

    @classmethod
    def _are_instances(cls, container):
        return all([
            isinstance(ele, cls._allowed_instances)
            for ele in container
        ])

    def __repr__(self):
        return (
            f"{type(self).__name__}("
            f"{'; '.join([ele.__repr__() for ele in self])})"
        )

    def __str__(self):
        joined_elements = ';\n\t'.join([ele.__str__() for ele in self])
        return (
            f"{type(self).__name__}(\n\t"
            f"{joined_elements})"
        )

    @property
    def container(self):
        return self._container

    def __iter__(self):
        return iter(self.container)

    def __len__(self):
        return len(self.container)

    def len(self):
        return len(self.container)

    def __getitem__(self, key):
        return self.container[key]

    def __call__(self, *args, iter_kwargs=None, **kwargs):
        container = [
            ele(*args, **kwargs)
            if iter_kwargs is None
            else ele(*args, **kwargs, **iter_kwargs[index])
            for index, ele in enumerate(self)
        ]
        if self._are_instances(container):
            return type(self)(container)
        else:
            return CallableList(container, container_class=type(self))

    def __getattr__(self, name):
        if '_container' in vars(self):
            container = [getattr(ele, name) for ele in self]
            if self._are_instances(container):
                return type(self)(container)
            else:
                return CallableList(container, container_class=type(self))
        else:
            raise AttributeError(
                f"'{type(self).__name__}' object has "
                f"not attribute '{name}'."
            )

    def to_dict(self):
        return self._container

    @classmethod
    def from_dict(cls, data):
        return cls(data)

    def _check_list(self, container):
        from dreye.utilities import is_listlike
        if is_listlike(container):
            container = list(container)
        else:
            raise DreyeError(
                'container must be a list-like.')
        if not self._are_instances(container):
            raise DreyeError(
                'not all elements of container are '
                f'of a {self._allowed_instances} instance.'
            )

        return container

    def _check_ele(self, ele):
        if not isinstance(ele, self._allowed_instances):
            raise DreyeError(
                f'New element of type {type(ele)} is'
                f'not a {self._allowed_instances} instance.'
            )

    def append(self, value):
        self._check_ele(value)
        self._container.append(value)
        self._init_attrs()

    def extend(self, value):
        value = self._check_list(value)
        self._container.extend(value)
        self._init_attrs()

    def pop(self, index=-1):
        value = self._container.pop(index)
        self._init_attrs()
        return value
