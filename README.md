# tsakorpus2eaf

This is a tool for transforming simple ELAN transcriptions and morphologically annotated representations of the same files in [tsakorpus](https://bitbucket.org/tsakorpus/tsakorpus/src) JSON into morphologically annotated ELAN files.

## Requirements

You need Python 3.x to run the conversion. See ``requirements.txt`` for the list of required modules.

## How to use

Create ``eaf`` and ``json`` folders inside repository root if they are not present. Put unannotated ELAN files in the ``eaf`` folder. Put their annotated Tsakorpus versions in the ``json`` folder. Run ``tsakorpus2kenlm.py``. Annotated versions will appear in ``eaf_analyzed``.

## License

The software is distributed under MIT license (see LICENSE.md).
