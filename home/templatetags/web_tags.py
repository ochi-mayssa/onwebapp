from django import template

register = template.Library()

@register.filter(name='str_split')
def str_split(value, arg):
    """Splits a string by the given delimiter."""
    return value.split(arg)
