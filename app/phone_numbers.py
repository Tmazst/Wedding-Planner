"""Country-aware phone parsing and presentation."""

from functools import lru_cache

import phonenumbers
import pycountry


PREFERRED_COUNTRIES = ("SZ", "ZA", "BW", "LS", "MZ", "ZW")


@lru_cache(maxsize=1)
def country_options():
    """Return ISO countries that have an assigned international calling code."""
    choices = []
    for country in pycountry.countries:
        region = country.alpha_2
        calling_code = phonenumbers.country_code_for_region(region)
        if calling_code:
            choices.append({
                "code": region,
                "name": country.name,
                "calling_code": f"+{calling_code}",
            })
    preference = {code: position for position, code in enumerate(PREFERRED_COUNTRIES)}
    choices.sort(key=lambda item: (
        preference.get(item["code"], len(preference)),
        item["name"],
    ))
    return tuple(choices)


def normalize_phone(value, country):
    """Validate and return an E.164 number and its ISO region."""
    region = (country or "").strip().upper()
    if len(region) != 2 or phonenumbers.country_code_for_region(region) == 0:
        raise ValueError("Choose a valid country or region.")
    try:
        parsed = phonenumbers.parse((value or "").strip(), region)
    except phonenumbers.NumberParseException as error:
        raise ValueError("Enter a valid mobile phone number.") from error
    if not phonenumbers.is_possible_number(parsed) or not phonenumbers.is_valid_number(parsed):
        raise ValueError("Enter a valid mobile phone number for the selected country.")
    detected_region = phonenumbers.region_code_for_number(parsed) or region
    if detected_region != region:
        raise ValueError("The phone number does not match the selected country.")
    return (
        phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164),
        detected_region,
    )


def format_phone_for_display(value, country=None):
    try:
        parsed = phonenumbers.parse(value, country)
        return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.INTERNATIONAL)
    except phonenumbers.NumberParseException:
        return value
