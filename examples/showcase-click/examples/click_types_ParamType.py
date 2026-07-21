from click.types import ParamType


class MyParamType(ParamType):
    def convert(self, value, param, ctx):
        return value


instance = MyParamType()
