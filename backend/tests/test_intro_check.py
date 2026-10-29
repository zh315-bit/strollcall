from app.services.grounding import intro_problems

SOURCE = ("Washington Square Park is a 9.75-acre public park in the Greenwich Village neighborhood of "
          "Lower Manhattan, New York City. One of the best known of New York City's 1,900 public parks, it is "
          "a landmark as well as a meeting place and center for cultural activity. The Washington Square Arch "
          "was built in 1892.")
NAME = "Washington Square Park"


def test_a_faithful_rewrite_passes():
    intro = ("Washington Square Park is a 9.75-acre public park in Greenwich Village. "
             "Its Washington Square Arch was built in 1892.")
    assert intro_problems(intro, SOURCE, NAME) == []


def test_invented_numbers_names_features_and_praise_fail():
    assert any("1889" in p for p in intro_problems("The arch was built in 1889.", SOURCE, NAME))
    assert any("Stanford" in p for p in intro_problems("It was designed by Stanford White.", SOURCE, NAME))
    assert any("fountain" in p for p in intro_problems("It has a fountain.", SOURCE, NAME))
    assert any("famous" in p for p in intro_problems("A famous park.", SOURCE, NAME))
    assert any("unverifiable" in p for p in intro_problems("A quiet park in the city.", SOURCE, NAME))


def test_length_and_sentence_limits():
    assert intro_problems("One. Two. Three.", SOURCE, NAME) == ["more than 2 sentences"]
    assert "longer than 300 characters" in intro_problems("park " * 80, SOURCE, NAME)


def test_initials_and_abbreviations_do_not_end_sentences():
    from app.services.grounding import sentences

    text = "A sculpture of U.S. Congressman John Watts by J. Leonard Corning near St. Paul's. It dates from 1890."
    assert len(sentences(text)) == 2


def test_curly_apostrophes_and_possessives_match_the_source():
    assert intro_problems("It is in Greenwich Village’s Washington Square Park.", SOURCE, NAME) == []
