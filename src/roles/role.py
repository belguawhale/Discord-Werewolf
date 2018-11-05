class Role:
    name = NotImplemented
    plural = NotImplemented
    description = NotImplemented
    team = NotImplemented

    def __eq__(self, other):
        if isinstance(other, Role) or issubclass(other, Role):
            return self.name == other.name
        elif isinstance(other, str):
            return self.name == other
        return False
