from click.decorators import confirmation_option


@confirmation_option()
def my_command():
    pass
