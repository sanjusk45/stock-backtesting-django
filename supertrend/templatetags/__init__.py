from django import template

register = template.Library()


@register.filter
def get_item(dictionary, key):
    """Allow {{ dict|get_item:'key with spaces' }} in templates."""
    if isinstance(dictionary, dict):
        return dictionary.get(key, '')
    return ''
