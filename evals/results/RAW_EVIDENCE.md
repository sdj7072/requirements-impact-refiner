# Raw evaluation evidence

The byte-preserved raw corpora — `baseline-raw/`, `with-skill-raw/`,
`integration-raw/`, `compatibility-raw/`, `installed-v0.3/raw/`,
`installed-v0.3.1/raw/`, and `installed-v0.3.1/controller.json` — live on
the **`evidence-v031`** branch, which seals them at the exact commit they
were last verified on. They were relocated because they added ~29 MB to
every plugin install while the shipped skill needs none of them at runtime.

Nothing was rewritten: the branch preserves the original bytes, and
`installed-v0.3.1/manifest.sha256` (kept here) still pins every file's
digest, so the relocated tree remains tamper-evident. To run the sealed
evidence tests:

~~~sh
git fetch origin evidence-v031
git checkout evidence-v031
python3 -m unittest discover -s tests -v
~~~

On branches without the raw corpora, those tests skip with an explicit
reason instead of failing.
