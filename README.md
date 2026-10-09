# paper-sift

A Claude Code plugin that builds a reading list for learning a research area. You name the topic;
Claude designs the search with you; a deterministic pipeline walks the Semantic Scholar citation
graph, screens every candidate on its full abstract with [TypeSafe's Jev](https://docs.typesafe.ai/),
reads the full text of the most promising papers, and writes a ranked list that explains why each
paper is on it.

> **Status:** under construction. The design is in [docs/design.md](docs/design.md).

Not affiliated with TypeSafe AI, Semantic Scholar or OpenAlex.

## License

[MIT](LICENSE)
