# Failure analysis on the test set

System read: hybrid search with `voyage-4-lite`, the run that also produced the cited answers. In that run, 130 of the 208 expected references were not in the top 10 (62 percent).

I drew 15 of those 130 at random (fixed seed) and read each pair: the query patent, the missed reference, and where the reference ranked when I searched deeper (100 candidates from each ranking). One reader, so the sorting is a judgment call.

| # | Query | Missed reference | Rank | Cause |
|---|---|---|---|---|
| 1 | Virtual AC power signals | Isolated power transfer via coupled oscillators | 29 | Other aspect: receiver oscillator circuit |
| 2 | Coil pattern groups on a power transmission unit | Antenna unit with an antenna pattern on a circuit board | 21 | Same idea, other words (coil, antenna) |
| 3 | Layered substrate with a soft magnetic layer | Shaping the field to allow positioning freedom | 23 | Other aspect: field control and not materials |
| 4 | Charging transmitters under a surface | Charger that shows the charging area with light | 15 | Other aspect: user display |
| 5 | Phone case with a receiver coil | Transmission coil module with shield and metal plate | 23 | Other side of the link (transmitter) and other aspect |
| 6 | Dual function coil in a vehicle | Bi-state impedance conversion | beyond 100 | Other aspect: circuit |
| 7 | Concave shaped coil surface | Charging module for a sensing device | beyond 100 | Other application |
| 8 | Heat dissipating plate for a coil | Thermal management in wireless power transfer | 9 | Same idea. Found at rank 9 with 100 candidates, missed with the 50 used in the run |
| 9 | Virtual AC power signals | Magnetic field with a shifted frequency | beyond 100 | Other aspect: frequency |
| 10 | Position detection for a charger | Smart power and data transfer system | beyond 100 | Other aspect |
| 11 | Wireless power transceiver with a controller | Variable resonant circuit | 43 | Other aspect: circuit |
| 12 | Concave shaped coil surface | Antenna pairs for power transmission | beyond 100 | Other aspect |
| 13 | Foldable phone housing and display | Charger that moves to find a device | 67 | The query is mostly not about charging |
| 14 | Inductive charger with separated electronics | Add-on module that turns a phone into a charger | 25 | The query abstract is one sentence |
| 15 | Power transfer to a mobile part through a floor | Charging assembly with a ferrimagnetic sleeve | beyond 100 | Other aspect |

By cause:

| Cause | Cases |
|---|---|
| The reference covers another aspect of wireless charging (circuit, structure, application, display) | 11 |
| Same idea in other words, or only just outside the top 10 | 2 |
| The query text is thin or mostly about something else | 2 |

What stands out:

- Most missed references are patents from the same field that an examiner cited as background, not patents that describe the same invention. Nothing that searches for the closest document would be expected to find them. This caps the recall of every system on this answer key, and it matches what I saw on the development set.
- 7 of the 15 rank between 9 and 29, close to the cut. Deeper candidate lists or a reranker could recover some of them. Case 8 shows it: it was missed only because the run fetched 50 candidates from each ranking, and it sits at rank 9 with 100.
- Case 13 is a query problem. A patent about a foldable phone is a poor query for a charging search, and my query is simply the patent abstract plus the first claim.
- Case 14 is a one sentence abstract.

Settings were not changed after reading these cases, and the test set was not used to tune anything.
