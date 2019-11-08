import duplicates

def test_init():
    df = duplicates.DupFinder(verbose=True)
    assert df.verbose == True

