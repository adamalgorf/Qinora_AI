from qinora.application.greeting import first_name, greeting


def test_uses_first_token_of_display_name() -> None:
    assert first_name("Adam Algorf", "adam@fivestarsmedia.se") == "Adam"


def test_falls_back_to_email_local_part_when_no_display_name() -> None:
    assert first_name(None, "adam.algorf@fivestarsmedia.se") == "Adam"
    assert first_name("", "farah@qinora.org") == "Farah"


def test_strips_digits_and_separators_from_local_part_guess() -> None:
    assert first_name(None, "adam123@example.com") == "Adam"
    assert first_name(None, "adam_algorf@example.com") == "Adam"


def test_greeting_includes_exclamation_and_name() -> None:
    assert greeting("Adam Algorf", "adam@example.com") == "Hej Adam!"


def test_greeting_falls_back_to_plain_hej_when_nothing_usable() -> None:
    assert greeting(None, "@invalid") == "Hej!"
