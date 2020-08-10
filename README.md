# tsakorpus2eaf

This is a tool for transforming simple [ELAN](https://archive.mpi.nl/tla/elan) transcriptions and morphologically annotated representations of the same files in [tsakorpus](https://bitbucket.org/tsakorpus/tsakorpus/src) JSON into morphologically annotated ELAN files.

## Requirements

You need Python 3.x to run the conversion. See ``requirements.txt`` for the list of required modules.

## How to use

Create ``conf``, ``eaf`` and ``json`` folders inside repository root if they are not present. Put unannotated ELAN files in the ``eaf`` folder. Put their annotated Tsakorpus versions in the ``json`` folder. Put ``corpus.json`` from the ``conf`` folder of your tsakorpus instance to ``conf``. (The program will need ``gr_fields_order`` value from the ``lang_props`` dictionary to be able to order grammatical tags correctly.) Change the values passed to the constructor, if needed. Run ``tsakorpus2kenlm.py``. Annotated versions will appear in ``eaf_analyzed``.

## Configuration

There are several configuration options.

* The most important is the regex that described which tiers contain the transcription to be analyzed. It is passed as a string to the constructor of ``EafProcessor`` class. Only those time-aligned tiers whose name or type match this regex will be processed.
* If you want the grammatical tags to be sorted nicely, you will have to provide a ``corpus.json`` file from your tsakorpus instance where the tag order is described (see [tsakorpus documentation](https://bitbucket.org/tsakorpus/tsakorpus/src/master/docs/configuration.md)). You will also have to pass the name of the language in the ``lang`` argument for the constructor.
* The constructor has optional arguments that determine how the tier types for tokens, lemmata etc. are going to be called. If you already have those tier types in your ELAN files, put their names there. Otherwise, new tier types and tiers will be created.

## License

The software is distributed under MIT license (see LICENSE.md).
