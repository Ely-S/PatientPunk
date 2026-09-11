# Frozen September 3 model appendix

Validated saved coefficients and statuses, not a refit. All intervals are 95%. The [main report](severity_checkpoint.md) defines units, scales, linkage, and limitations. Nominal p values are exploratory; this table does not apply an additional multiple-testing correction.

Historical model adequacy has not been revalidated. Some pooled compound terms, including Cerebrolysin and 9-MBC, have near-zero estimates and confidence limits. These are unstable or degenerate nuisance terms in sparse models, not evidence of absent adverse risk. Interpret neither their tiny nominal p values nor their apparent precision as clinical findings.

## any side effect

| Scope | Compound | Model | Observations | Author clusters | Term | Scale | Estimate (95% CI) | p |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| treatment-specific | 7,8-DHF | dose only | 48 | 48 | intercept | odds ratio | 2.76 (0.10 to 76.44) | 0.5486 |
| treatment-specific | 7,8-DHF | dose only | 48 | 48 | log2 dose (per doubling) | odds ratio | 0.82 (0.40 to 1.67) | 0.5766 |
| treatment-specific | BPC-157 | dose only | 919 | 919 | intercept | odds ratio | 0.59 (0.44 to 0.78) | 0.0003 |
| treatment-specific | BPC-157 | dose only | 919 | 919 | log2 dose (per doubling) | odds ratio | 0.81 (0.69 to 0.97) | 0.0186 |
| treatment-specific | Dihexa | dose only | 26 | 26 | intercept | odds ratio | 3.69 (0.22 to 62.22) | 0.3649 |
| treatment-specific | Dihexa | dose only | 26 | 26 | log2 dose (per doubling) | odds ratio | 0.73 (0.34 to 1.53) | 0.4028 |
| treatment-specific | Lion's mane | dose only | 460 | 460 | intercept | odds ratio | 1.18 (0.22 to 6.29) | 0.8430 |
| treatment-specific | Lion's mane | dose only | 460 | 460 | log2 dose (per doubling) | odds ratio | 0.93 (0.78 to 1.10) | 0.3822 |
| treatment-specific | NSI-189 | dose only | 64 | 64 | intercept | odds ratio | 76.58 (0.68 to 8620.83) | 0.0718 |
| treatment-specific | NSI-189 | dose only | 64 | 64 | log2 dose (per doubling) | odds ratio | 0.44 (0.17 to 1.11) | 0.0823 |
| treatment-specific | Selank | dose only | 138 | 138 | intercept | odds ratio | 0.20 (0.08 to 0.49) | 0.0005 |
| treatment-specific | Selank | dose only | 138 | 138 | log2 dose (per doubling) | odds ratio | 0.62 (0.39 to 0.99) | 0.0472 |
| treatment-specific | Semax | dose only | 195 | 195 | intercept | odds ratio | 0.63 (0.42 to 0.95) | 0.0286 |
| treatment-specific | Semax | dose only | 195 | 195 | log2 dose (per doubling) | odds ratio | 0.94 (0.73 to 1.20) | 0.6189 |
| pooled with compound fixed effects | all compounds | dose only | 1876 | 1766 | intercept | odds ratio | 0.61 (0.50 to 0.75) | <0.0001 |
| pooled with compound fixed effects | all compounds | dose only | 1876 | 1766 | log2 dose (per doubling) | odds ratio | 0.84 (0.76 to 0.93) | 0.0012 |
| pooled with compound fixed effects | all compounds | dose only | 1876 | 1766 | compound: 4'-DMA vs BPC-157 | odds ratio | 2.69 (0.86 to 8.39) | 0.0875 |
| pooled with compound fixed effects | all compounds | dose only | 1876 | 1766 | compound: 7,8-DHF vs BPC-157 | odds ratio | 3.95 (1.66 to 9.40) | 0.0019 |
| pooled with compound fixed effects | all compounds | dose only | 1876 | 1766 | compound: 9-MBC vs BPC-157 | odds ratio | 3.23 (0.74 to 14.18) | 0.1196 |
| pooled with compound fixed effects | all compounds | dose only | 1876 | 1766 | compound: Cerebrolysin vs BPC-157 | odds ratio | 1.4e-10 (4.3e-11 to 4.9e-10) | <0.0001 |
| pooled with compound fixed effects | all compounds | dose only | 1876 | 1766 | compound: Dihexa vs BPC-157 | odds ratio | 3.58 (1.39 to 9.18) | 0.0081 |
| pooled with compound fixed effects | all compounds | dose only | 1876 | 1766 | compound: Lion's mane vs BPC-157 | odds ratio | 5.10 (1.52 to 17.07) | 0.0083 |
| pooled with compound fixed effects | all compounds | dose only | 1876 | 1766 | compound: NSI-189 vs BPC-157 | odds ratio | 4.49 (1.91 to 10.57) | 0.0006 |
| pooled with compound fixed effects | all compounds | dose only | 1876 | 1766 | compound: Selank vs BPC-157 | odds ratio | 0.53 (0.36 to 0.77) | 0.0010 |
| pooled with compound fixed effects | all compounds | dose only | 1876 | 1766 | compound: Semax vs BPC-157 | odds ratio | 0.90 (0.66 to 1.24) | 0.5232 |
| treatment-specific | BPC-157 | route only | 1169 | 1169 | intercept | odds ratio | 0.83 (0.72 to 0.96) | 0.0095 |
| treatment-specific | BPC-157 | route only | 1169 | 1169 | route: dermal vs parenteral | odds ratio | 0.96 (0.26 to 3.61) | 0.9550 |
| treatment-specific | BPC-157 | route only | 1169 | 1169 | route: nasal vs parenteral | odds ratio | 0.84 (0.48 to 1.45) | 0.5311 |
| treatment-specific | BPC-157 | route only | 1169 | 1169 | route: oral vs parenteral | odds ratio | 0.78 (0.60 to 1.02) | 0.0663 |
| treatment-specific | Cerebrolysin | route only | 71 | 71 | intercept | odds ratio | 0.59 (0.35 to 0.99) | 0.0446 |
| treatment-specific | Cerebrolysin | route only | 71 | 71 | route: nasal vs parenteral | odds ratio | 0.48 (0.09 to 2.53) | 0.3904 |
| treatment-specific | Dihexa | route only | 30 | 30 | intercept | odds ratio | 1.00 (0.42 to 2.40) | 1.0000 |
| treatment-specific | Dihexa | route only | 30 | 30 | route: dermal vs oral | odds ratio | 1.00 (0.22 to 4.56) | 1.0000 |
| treatment-specific | Selank | route only | 214 | 214 | intercept | odds ratio | 0.43 (0.31 to 0.61) | <0.0001 |
| treatment-specific | Selank | route only | 214 | 214 | route: parenteral vs nasal | odds ratio | 0.80 (0.41 to 1.56) | 0.5149 |
| treatment-specific | Semax | route only | 281 | 281 | intercept | odds ratio | 0.56 (0.42 to 0.75) | <0.0001 |
| treatment-specific | Semax | route only | 281 | 281 | route: parenteral vs nasal | odds ratio | 1.01 (0.59 to 1.73) | 0.9636 |
| pooled with compound fixed effects | all compounds | route only | 1902 | 1720 | intercept | odds ratio | 0.82 (0.71 to 0.94) | 0.0038 |
| pooled with compound fixed effects | all compounds | route only | 1902 | 1720 | route: dermal vs parenteral | odds ratio | 1.02 (0.38 to 2.74) | 0.9720 |
| pooled with compound fixed effects | all compounds | route only | 1902 | 1720 | route: nasal vs parenteral | odds ratio | 0.93 (0.67 to 1.29) | 0.6430 |
| pooled with compound fixed effects | all compounds | route only | 1902 | 1720 | route: oral vs parenteral | odds ratio | 0.82 (0.63 to 1.06) | 0.1247 |
| pooled with compound fixed effects | all compounds | route only | 1902 | 1720 | compound: 4'-DMA vs BPC-157 | odds ratio | 1.33 (0.50 to 3.55) | 0.5637 |
| pooled with compound fixed effects | all compounds | route only | 1902 | 1720 | compound: 7,8-DHF vs BPC-157 | odds ratio | 1.61 (0.90 to 2.87) | 0.1051 |
| pooled with compound fixed effects | all compounds | route only | 1902 | 1720 | compound: 9-MBC vs BPC-157 | odds ratio | 1.13 (0.25 to 5.11) | 0.8784 |
| pooled with compound fixed effects | all compounds | route only | 1902 | 1720 | compound: Cerebrolysin vs BPC-157 | odds ratio | 0.67 (0.41 to 1.11) | 0.1224 |
| pooled with compound fixed effects | all compounds | route only | 1902 | 1720 | compound: Dihexa vs BPC-157 | odds ratio | 1.16 (0.55 to 2.44) | 0.6922 |
| pooled with compound fixed effects | all compounds | route only | 1902 | 1720 | compound: Lion's mane vs BPC-157 | odds ratio | 1.77 (0.77 to 4.08) | 0.1777 |
| pooled with compound fixed effects | all compounds | route only | 1902 | 1720 | compound: NSI-189 vs BPC-157 | odds ratio | 3.59 (1.46 to 8.80) | 0.0052 |
| pooled with compound fixed effects | all compounds | route only | 1902 | 1720 | compound: Selank vs BPC-157 | odds ratio | 0.53 (0.37 to 0.78) | 0.0011 |
| pooled with compound fixed effects | all compounds | route only | 1902 | 1720 | compound: Semax vs BPC-157 | odds ratio | 0.73 (0.52 to 1.03) | 0.0745 |
| treatment-specific | BPC-157 | dose + route | 417 | 417 | intercept | odds ratio | 0.73 (0.46 to 1.15) | 0.1746 |
| treatment-specific | BPC-157 | dose + route | 417 | 417 | log2 dose (per doubling) | odds ratio | 0.84 (0.64 to 1.09) | 0.1925 |
| treatment-specific | BPC-157 | dose + route | 417 | 417 | route: nasal vs parenteral | odds ratio | 1.66 (0.50 to 5.54) | 0.4073 |
| treatment-specific | BPC-157 | dose + route | 417 | 417 | route: oral vs parenteral | odds ratio | 1.28 (0.77 to 2.12) | 0.3398 |
| treatment-specific | Selank | dose + route | 54 | 54 | intercept | odds ratio | 0.41 (0.11 to 1.53) | 0.1835 |
| treatment-specific | Selank | dose + route | 54 | 54 | log2 dose (per doubling) | odds ratio | 0.50 (0.25 to 1.01) | 0.0548 |
| treatment-specific | Selank | dose + route | 54 | 54 | route: parenteral vs nasal | odds ratio | 0.34 (0.10 to 1.19) | 0.0924 |
| treatment-specific | Semax | dose + route | 70 | 70 | intercept | odds ratio | 0.78 (0.37 to 1.62) | 0.5022 |
| treatment-specific | Semax | dose + route | 70 | 70 | log2 dose (per doubling) | odds ratio | 1.02 (0.72 to 1.43) | 0.9211 |
| treatment-specific | Semax | dose + route | 70 | 70 | route: parenteral vs nasal | odds ratio | 1.12 (0.42 to 2.99) | 0.8203 |
| pooled with compound fixed effects | all compounds | dose + route | 607 | 568 | intercept | odds ratio | 0.68 (0.47 to 0.98) | 0.0404 |
| pooled with compound fixed effects | all compounds | dose + route | 607 | 568 | log2 dose (per doubling) | odds ratio | 0.80 (0.65 to 0.97) | 0.0249 |
| pooled with compound fixed effects | all compounds | dose + route | 607 | 568 | route: nasal vs parenteral | odds ratio | 1.55 (0.79 to 3.03) | 0.2011 |
| pooled with compound fixed effects | all compounds | dose + route | 607 | 568 | route: oral vs parenteral | odds ratio | 1.26 (0.78 to 2.05) | 0.3492 |
| pooled with compound fixed effects | all compounds | dose + route | 607 | 568 | compound: 4'-DMA vs BPC-157 | odds ratio | 6.68 (0.99 to 44.86) | 0.0506 |
| pooled with compound fixed effects | all compounds | dose + route | 607 | 568 | compound: 7,8-DHF vs BPC-157 | odds ratio | 4.38 (1.00 to 19.10) | 0.0495 |
| pooled with compound fixed effects | all compounds | dose + route | 607 | 568 | compound: 9-MBC vs BPC-157 | odds ratio | 2e-10 (1.9e-11 to 2e-09) | <0.0001 |
| pooled with compound fixed effects | all compounds | dose + route | 607 | 568 | compound: Cerebrolysin vs BPC-157 | odds ratio | 1.5e-10 (3e-11 to 7.5e-10) | <0.0001 |
| pooled with compound fixed effects | all compounds | dose + route | 607 | 568 | compound: Dihexa vs BPC-157 | odds ratio | 3.76 (0.80 to 17.78) | 0.0944 |
| pooled with compound fixed effects | all compounds | dose + route | 607 | 568 | compound: Lion's mane vs BPC-157 | odds ratio | 4.54 (0.30 to 69.04) | 0.2758 |
| pooled with compound fixed effects | all compounds | dose + route | 607 | 568 | compound: NSI-189 vs BPC-157 | odds ratio | 4.46 (0.88 to 22.54) | 0.0708 |
| pooled with compound fixed effects | all compounds | dose + route | 607 | 568 | compound: Selank vs BPC-157 | odds ratio | 0.63 (0.32 to 1.24) | 0.1777 |
| pooled with compound fixed effects | all compounds | dose + route | 607 | 568 | compound: Semax vs BPC-157 | odds ratio | 0.66 (0.34 to 1.29) | 0.2215 |
| treatment-specific | BPC-157 | dose + route + interaction | 417 | 417 | intercept | odds ratio | 0.64 (0.39 to 1.05) | 0.0801 |
| treatment-specific | BPC-157 | dose + route + interaction | 417 | 417 | log2 dose (per doubling) | odds ratio | 0.77 (0.57 to 1.03) | 0.0825 |
| treatment-specific | BPC-157 | dose + route + interaction | 417 | 417 | route: nasal vs parenteral | odds ratio | 10.05 (0.93 to 108.10) | 0.0569 |
| treatment-specific | BPC-157 | dose + route + interaction | 417 | 417 | route: oral vs parenteral | odds ratio | 1.31 (0.42 to 4.11) | 0.6384 |
| treatment-specific | BPC-157 | dose + route + interaction | 417 | 417 | dose x route: nasal vs parenteral | odds ratio | 3.01 (1.09 to 8.37) | 0.0341 |
| treatment-specific | BPC-157 | dose + route + interaction | 417 | 417 | dose x route: oral vs parenteral | odds ratio | 1.01 (0.46 to 2.22) | 0.9859 |
| treatment-specific | Selank | dose + route + interaction | 54 | 54 | intercept | odds ratio | 0.46 (0.12 to 1.80) | 0.2622 |
| treatment-specific | Selank | dose + route + interaction | 54 | 54 | log2 dose (per doubling) | odds ratio | 0.54 (0.26 to 1.15) | 0.1087 |
| treatment-specific | Selank | dose + route + interaction | 54 | 54 | route: parenteral vs nasal | odds ratio | 0.20 (0.01 to 6.14) | 0.3560 |
| treatment-specific | Selank | dose + route + interaction | 54 | 54 | dose x route: parenteral vs nasal | odds ratio | 0.70 (0.12 to 4.21) | 0.7013 |
| treatment-specific | Semax | dose + route + interaction | 70 | 70 | intercept | odds ratio | 0.76 (0.35 to 1.63) | 0.4759 |
| treatment-specific | Semax | dose + route + interaction | 70 | 70 | log2 dose (per doubling) | odds ratio | 1.00 (0.68 to 1.45) | 0.9879 |
| treatment-specific | Semax | dose + route + interaction | 70 | 70 | route: parenteral vs nasal | odds ratio | 1.24 (0.35 to 4.44) | 0.7420 |
| treatment-specific | Semax | dose + route + interaction | 70 | 70 | dose x route: parenteral vs nasal | odds ratio | 1.11 (0.46 to 2.65) | 0.8155 |
| pooled with compound fixed effects | all compounds | dose + route + interaction | 607 | 568 | intercept | odds ratio | 0.62 (0.39 to 0.99) | 0.0461 |
| pooled with compound fixed effects | all compounds | dose + route + interaction | 607 | 568 | log2 dose (per doubling) | odds ratio | 0.75 (0.56 to 0.99) | 0.0423 |
| pooled with compound fixed effects | all compounds | dose + route + interaction | 607 | 568 | route: nasal vs parenteral | odds ratio | 2.02 (0.84 to 4.87) | 0.1174 |
| pooled with compound fixed effects | all compounds | dose + route + interaction | 607 | 568 | route: oral vs parenteral | odds ratio | 1.10 (0.48 to 2.53) | 0.8209 |
| pooled with compound fixed effects | all compounds | dose + route + interaction | 607 | 568 | dose x route: nasal vs parenteral | odds ratio | 1.24 (0.81 to 1.88) | 0.3201 |
| pooled with compound fixed effects | all compounds | dose + route + interaction | 607 | 568 | dose x route: oral vs parenteral | odds ratio | 0.87 (0.52 to 1.46) | 0.6019 |
| pooled with compound fixed effects | all compounds | dose + route + interaction | 607 | 568 | compound: 4'-DMA vs BPC-157 | odds ratio | 17.54 (1.34 to 229.74) | 0.0291 |
| pooled with compound fixed effects | all compounds | dose + route + interaction | 607 | 568 | compound: 7,8-DHF vs BPC-157 | odds ratio | 13.69 (0.99 to 188.84) | 0.0506 |
| pooled with compound fixed effects | all compounds | dose + route + interaction | 607 | 568 | compound: 9-MBC vs BPC-157 | odds ratio | 6.3e-10 (2.5e-11 to 1.6e-08) | <0.0001 |
| pooled with compound fixed effects | all compounds | dose + route + interaction | 607 | 568 | compound: Cerebrolysin vs BPC-157 | odds ratio | 1.9e-10 (3.2e-11 to 1.2e-09) | <0.0001 |
| pooled with compound fixed effects | all compounds | dose + route + interaction | 607 | 568 | compound: Dihexa vs BPC-157 | odds ratio | 9.25 (0.84 to 102.13) | 0.0694 |
| pooled with compound fixed effects | all compounds | dose + route + interaction | 607 | 568 | compound: Lion's mane vs BPC-157 | odds ratio | 33.33 (0.25 to 4396.05) | 0.1592 |
| pooled with compound fixed effects | all compounds | dose + route + interaction | 607 | 568 | compound: NSI-189 vs BPC-157 | odds ratio | 13.60 (0.85 to 218.82) | 0.0655 |
| pooled with compound fixed effects | all compounds | dose + route + interaction | 607 | 568 | compound: Selank vs BPC-157 | odds ratio | 0.65 (0.33 to 1.28) | 0.2153 |
| pooled with compound fixed effects | all compounds | dose + route + interaction | 607 | 568 | compound: Semax vs BPC-157 | odds ratio | 0.67 (0.35 to 1.31) | 0.2461 |

## distinct side-effect count

| Scope | Compound | Model | Observations | Author clusters | Term | Scale | Estimate (95% CI) | p |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| treatment-specific | 7,8-DHF | dose only | 48 | 48 | intercept | incidence-rate ratio | 0.92 (0.12 to 7.20) | 0.9380 |
| treatment-specific | 7,8-DHF | dose only | 48 | 48 | log2 dose (per doubling) | incidence-rate ratio | 1.01 (0.65 to 1.58) | 0.9534 |
| treatment-specific | BPC-157 | dose only | 919 | 919 | intercept | incidence-rate ratio | 0.64 (0.50 to 0.83) | 0.0005 |
| treatment-specific | BPC-157 | dose only | 919 | 919 | log2 dose (per doubling) | incidence-rate ratio | 0.81 (0.70 to 0.94) | 0.0053 |
| treatment-specific | Dihexa | dose only | 26 | 26 | intercept | incidence-rate ratio | 0.75 (0.18 to 3.22) | 0.7008 |
| treatment-specific | Dihexa | dose only | 26 | 26 | log2 dose (per doubling) | incidence-rate ratio | 1.01 (0.65 to 1.55) | 0.9770 |
| treatment-specific | Lion's mane | dose only | 460 | 460 | intercept | incidence-rate ratio | 3.54 (0.89 to 14.01) | 0.0721 |
| treatment-specific | Lion's mane | dose only | 460 | 460 | log2 dose (per doubling) | incidence-rate ratio | 0.85 (0.74 to 0.98) | 0.0227 |
| treatment-specific | NSI-189 | dose only | 64 | 64 | intercept | incidence-rate ratio | 3.39 (0.13 to 88.92) | 0.4644 |
| treatment-specific | NSI-189 | dose only | 64 | 64 | log2 dose (per doubling) | incidence-rate ratio | 0.82 (0.42 to 1.59) | 0.5481 |
| treatment-specific | Selank | dose only | 138 | 138 | intercept | incidence-rate ratio | 0.28 (0.13 to 0.63) | 0.0019 |
| treatment-specific | Selank | dose only | 138 | 138 | log2 dose (per doubling) | incidence-rate ratio | 0.69 (0.47 to 1.03) | 0.0666 |
| treatment-specific | Semax | dose only | 195 | 195 | intercept | incidence-rate ratio | 0.81 (0.57 to 1.14) | 0.2238 |
| treatment-specific | Semax | dose only | 195 | 195 | log2 dose (per doubling) | incidence-rate ratio | 1.00 (0.82 to 1.22) | 0.9757 |
| pooled with compound fixed effects | all compounds | dose only | 1876 | 1766 | intercept | incidence-rate ratio | 0.69 (0.59 to 0.82) | <0.0001 |
| pooled with compound fixed effects | all compounds | dose only | 1876 | 1766 | log2 dose (per doubling) | incidence-rate ratio | 0.85 (0.78 to 0.93) | 0.0002 |
| pooled with compound fixed effects | all compounds | dose only | 1876 | 1766 | compound: 4'-DMA vs BPC-157 | incidence-rate ratio | 2.99 (1.30 to 6.87) | 0.0098 |
| pooled with compound fixed effects | all compounds | dose only | 1876 | 1766 | compound: 7,8-DHF vs BPC-157 | incidence-rate ratio | 3.01 (1.58 to 5.74) | 0.0008 |
| pooled with compound fixed effects | all compounds | dose only | 1876 | 1766 | compound: 9-MBC vs BPC-157 | incidence-rate ratio | 1.36 (0.59 to 3.10) | 0.4704 |
| pooled with compound fixed effects | all compounds | dose only | 1876 | 1766 | compound: Cerebrolysin vs BPC-157 | incidence-rate ratio | 2.5e-10 (7.6e-11 to 8.1e-10) | <0.0001 |
| pooled with compound fixed effects | all compounds | dose only | 1876 | 1766 | compound: Dihexa vs BPC-157 | incidence-rate ratio | 2.01 (1.07 to 3.77) | 0.0291 |
| pooled with compound fixed effects | all compounds | dose only | 1876 | 1766 | compound: Lion's mane vs BPC-157 | incidence-rate ratio | 5.23 (1.92 to 14.27) | 0.0012 |
| pooled with compound fixed effects | all compounds | dose only | 1876 | 1766 | compound: NSI-189 vs BPC-157 | incidence-rate ratio | 4.03 (2.17 to 7.50) | <0.0001 |
| pooled with compound fixed effects | all compounds | dose only | 1876 | 1766 | compound: Selank vs BPC-157 | incidence-rate ratio | 0.58 (0.42 to 0.80) | 0.0008 |
| pooled with compound fixed effects | all compounds | dose only | 1876 | 1766 | compound: Semax vs BPC-157 | incidence-rate ratio | 0.96 (0.74 to 1.23) | 0.7430 |
| treatment-specific | BPC-157 | route only | 1169 | 1169 | intercept | incidence-rate ratio | 0.85 (0.76 to 0.94) | 0.0024 |
| treatment-specific | BPC-157 | route only | 1169 | 1169 | route: dermal vs parenteral | incidence-rate ratio | 0.52 (0.25 to 1.10) | 0.0861 |
| treatment-specific | BPC-157 | route only | 1169 | 1169 | route: nasal vs parenteral | incidence-rate ratio | 0.86 (0.59 to 1.27) | 0.4571 |
| treatment-specific | BPC-157 | route only | 1169 | 1169 | route: oral vs parenteral | incidence-rate ratio | 1.02 (0.82 to 1.27) | 0.8809 |
| treatment-specific | Cerebrolysin | route only | 71 | 71 | intercept | incidence-rate ratio | 0.56 (0.38 to 0.85) | 0.0061 |
| treatment-specific | Cerebrolysin | route only | 71 | 71 | route: nasal vs parenteral | incidence-rate ratio | 0.79 (0.22 to 2.86) | 0.7161 |
| treatment-specific | Dihexa | route only | 30 | 30 | intercept | incidence-rate ratio | 0.80 (0.47 to 1.37) | 0.4152 |
| treatment-specific | Dihexa | route only | 30 | 30 | route: dermal vs oral | incidence-rate ratio | 1.25 (0.46 to 3.36) | 0.6586 |
| treatment-specific | Selank | route only | 214 | 214 | intercept | incidence-rate ratio | 0.47 (0.35 to 0.63) | <0.0001 |
| treatment-specific | Selank | route only | 214 | 214 | route: parenteral vs nasal | incidence-rate ratio | 0.83 (0.48 to 1.42) | 0.4964 |
| treatment-specific | Semax | route only | 281 | 281 | intercept | incidence-rate ratio | 0.71 (0.55 to 0.92) | 0.0097 |
| treatment-specific | Semax | route only | 281 | 281 | route: parenteral vs nasal | incidence-rate ratio | 0.91 (0.56 to 1.50) | 0.7199 |
| pooled with compound fixed effects | all compounds | route only | 1902 | 1720 | intercept | incidence-rate ratio | 0.84 (0.76 to 0.93) | 0.0011 |
| pooled with compound fixed effects | all compounds | route only | 1902 | 1720 | route: dermal vs parenteral | incidence-rate ratio | 0.87 (0.46 to 1.63) | 0.6565 |
| pooled with compound fixed effects | all compounds | route only | 1902 | 1720 | route: nasal vs parenteral | incidence-rate ratio | 1.02 (0.80 to 1.31) | 0.8699 |
| pooled with compound fixed effects | all compounds | route only | 1902 | 1720 | route: oral vs parenteral | incidence-rate ratio | 1.01 (0.82 to 1.26) | 0.8971 |
| pooled with compound fixed effects | all compounds | route only | 1902 | 1720 | compound: 4'-DMA vs BPC-157 | incidence-rate ratio | 1.17 (0.58 to 2.36) | 0.6530 |
| pooled with compound fixed effects | all compounds | route only | 1902 | 1720 | compound: 7,8-DHF vs BPC-157 | incidence-rate ratio | 1.09 (0.74 to 1.59) | 0.6714 |
| pooled with compound fixed effects | all compounds | route only | 1902 | 1720 | compound: 9-MBC vs BPC-157 | incidence-rate ratio | 1.34 (0.43 to 4.17) | 0.6119 |
| pooled with compound fixed effects | all compounds | route only | 1902 | 1720 | compound: Cerebrolysin vs BPC-157 | incidence-rate ratio | 0.65 (0.44 to 0.97) | 0.0370 |
| pooled with compound fixed effects | all compounds | route only | 1902 | 1720 | compound: Dihexa vs BPC-157 | incidence-rate ratio | 1.02 (0.64 to 1.62) | 0.9303 |
| pooled with compound fixed effects | all compounds | route only | 1902 | 1720 | compound: Lion's mane vs BPC-157 | incidence-rate ratio | 1.61 (0.99 to 2.63) | 0.0548 |
| pooled with compound fixed effects | all compounds | route only | 1902 | 1720 | compound: NSI-189 vs BPC-157 | incidence-rate ratio | 1.37 (0.86 to 2.17) | 0.1836 |
| pooled with compound fixed effects | all compounds | route only | 1902 | 1720 | compound: Selank vs BPC-157 | incidence-rate ratio | 0.52 (0.39 to 0.70) | <0.0001 |
| pooled with compound fixed effects | all compounds | route only | 1902 | 1720 | compound: Semax vs BPC-157 | incidence-rate ratio | 0.81 (0.61 to 1.07) | 0.1398 |
| treatment-specific | BPC-157 | dose + route | 417 | 417 | intercept | incidence-rate ratio | 0.68 (0.48 to 0.94) | 0.0215 |
| treatment-specific | BPC-157 | dose + route | 417 | 417 | log2 dose (per doubling) | incidence-rate ratio | 0.81 (0.66 to 0.99) | 0.0351 |
| treatment-specific | BPC-157 | dose + route | 417 | 417 | route: nasal vs parenteral | incidence-rate ratio | 1.38 (0.79 to 2.44) | 0.2617 |
| treatment-specific | BPC-157 | dose + route | 417 | 417 | route: oral vs parenteral | incidence-rate ratio | 1.43 (1.02 to 2.00) | 0.0358 |
| treatment-specific | Selank | dose + route | 54 | 54 | intercept | incidence-rate ratio | 0.49 (0.19 to 1.23) | 0.1291 |
| treatment-specific | Selank | dose + route | 54 | 54 | log2 dose (per doubling) | incidence-rate ratio | 0.72 (0.48 to 1.07) | 0.1068 |
| treatment-specific | Selank | dose + route | 54 | 54 | route: parenteral vs nasal | incidence-rate ratio | 0.53 (0.22 to 1.27) | 0.1558 |
| treatment-specific | Semax | dose + route | 70 | 70 | intercept | incidence-rate ratio | 1.37 (0.79 to 2.39) | 0.2610 |
| treatment-specific | Semax | dose + route | 70 | 70 | log2 dose (per doubling) | incidence-rate ratio | 1.11 (0.89 to 1.39) | 0.3608 |
| treatment-specific | Semax | dose + route | 70 | 70 | route: parenteral vs nasal | incidence-rate ratio | 0.59 (0.29 to 1.19) | 0.1413 |
| pooled with compound fixed effects | all compounds | dose + route | 607 | 568 | intercept | incidence-rate ratio | 0.74 (0.58 to 0.94) | 0.0135 |
| pooled with compound fixed effects | all compounds | dose + route | 607 | 568 | log2 dose (per doubling) | incidence-rate ratio | 0.86 (0.75 to 0.98) | 0.0264 |
| pooled with compound fixed effects | all compounds | dose + route | 607 | 568 | route: nasal vs parenteral | incidence-rate ratio | 1.62 (1.10 to 2.40) | 0.0156 |
| pooled with compound fixed effects | all compounds | dose + route | 607 | 568 | route: oral vs parenteral | incidence-rate ratio | 1.42 (1.03 to 1.96) | 0.0323 |
| pooled with compound fixed effects | all compounds | dose + route | 607 | 568 | compound: 4'-DMA vs BPC-157 | incidence-rate ratio | 2.93 (1.05 to 8.14) | 0.0393 |
| pooled with compound fixed effects | all compounds | dose + route | 607 | 568 | compound: 7,8-DHF vs BPC-157 | incidence-rate ratio | 2.04 (0.76 to 5.47) | 0.1548 |
| pooled with compound fixed effects | all compounds | dose + route | 607 | 568 | compound: 9-MBC vs BPC-157 | incidence-rate ratio | 1e-10 (1.2e-11 to 8.5e-10) | <0.0001 |
| pooled with compound fixed effects | all compounds | dose + route | 607 | 568 | compound: Cerebrolysin vs BPC-157 | incidence-rate ratio | 1e-10 (2.3e-11 to 4.5e-10) | <0.0001 |
| pooled with compound fixed effects | all compounds | dose + route | 607 | 568 | compound: Dihexa vs BPC-157 | incidence-rate ratio | 1.40 (0.55 to 3.55) | 0.4764 |
| pooled with compound fixed effects | all compounds | dose + route | 607 | 568 | compound: Lion's mane vs BPC-157 | incidence-rate ratio | 4.16 (0.65 to 26.50) | 0.1318 |
| pooled with compound fixed effects | all compounds | dose + route | 607 | 568 | compound: NSI-189 vs BPC-157 | incidence-rate ratio | 2.12 (0.73 to 6.21) | 0.1687 |
| pooled with compound fixed effects | all compounds | dose + route | 607 | 568 | compound: Selank vs BPC-157 | incidence-rate ratio | 0.53 (0.34 to 0.84) | 0.0070 |
| pooled with compound fixed effects | all compounds | dose + route | 607 | 568 | compound: Semax vs BPC-157 | incidence-rate ratio | 0.85 (0.58 to 1.26) | 0.4286 |
| treatment-specific | BPC-157 | dose + route + interaction | 417 | 417 | intercept | incidence-rate ratio | 0.65 (0.43 to 0.96) | 0.0320 |
| treatment-specific | BPC-157 | dose + route + interaction | 417 | 417 | log2 dose (per doubling) | incidence-rate ratio | 0.78 (0.62 to 1.00) | 0.0487 |
| treatment-specific | BPC-157 | dose + route + interaction | 417 | 417 | route: nasal vs parenteral | incidence-rate ratio | 3.60 (1.74 to 7.45) | 0.0005 |
| treatment-specific | BPC-157 | dose + route + interaction | 417 | 417 | route: oral vs parenteral | incidence-rate ratio | 1.17 (0.56 to 2.45) | 0.6775 |
| treatment-specific | BPC-157 | dose + route + interaction | 417 | 417 | dose x route: nasal vs parenteral | incidence-rate ratio | 2.07 (1.30 to 3.31) | 0.0023 |
| treatment-specific | BPC-157 | dose + route + interaction | 417 | 417 | dose x route: oral vs parenteral | incidence-rate ratio | 0.86 (0.52 to 1.41) | 0.5447 |
| treatment-specific | Selank | dose + route + interaction | 54 | 54 | intercept | incidence-rate ratio | 0.55 (0.22 to 1.37) | 0.2030 |
| treatment-specific | Selank | dose + route + interaction | 54 | 54 | log2 dose (per doubling) | incidence-rate ratio | 0.77 (0.50 to 1.18) | 0.2325 |
| treatment-specific | Selank | dose + route + interaction | 54 | 54 | route: parenteral vs nasal | incidence-rate ratio | 0.26 (0.03 to 1.95) | 0.1898 |
| treatment-specific | Selank | dose + route + interaction | 54 | 54 | dose x route: parenteral vs nasal | incidence-rate ratio | 0.66 (0.28 to 1.57) | 0.3483 |
| treatment-specific | Semax | dose + route + interaction | 70 | 70 | intercept | incidence-rate ratio | 1.50 (0.89 to 2.55) | 0.1296 |
| treatment-specific | Semax | dose + route + interaction | 70 | 70 | log2 dose (per doubling) | incidence-rate ratio | 1.21 (0.94 to 1.55) | 0.1395 |
| treatment-specific | Semax | dose + route + interaction | 70 | 70 | route: parenteral vs nasal | incidence-rate ratio | 0.40 (0.16 to 0.98) | 0.0453 |
| treatment-specific | Semax | dose + route + interaction | 70 | 70 | dose x route: parenteral vs nasal | incidence-rate ratio | 0.68 (0.35 to 1.31) | 0.2508 |
| pooled with compound fixed effects | all compounds | dose + route + interaction | 607 | 568 | intercept | incidence-rate ratio | 0.61 (0.43 to 0.87) | 0.0063 |
| pooled with compound fixed effects | all compounds | dose + route + interaction | 607 | 568 | log2 dose (per doubling) | incidence-rate ratio | 0.76 (0.62 to 0.94) | 0.0099 |
| pooled with compound fixed effects | all compounds | dose + route + interaction | 607 | 568 | route: nasal vs parenteral | incidence-rate ratio | 2.33 (1.35 to 4.01) | 0.0023 |
| pooled with compound fixed effects | all compounds | dose + route + interaction | 607 | 568 | route: oral vs parenteral | incidence-rate ratio | 1.55 (0.97 to 2.49) | 0.0663 |
| pooled with compound fixed effects | all compounds | dose + route + interaction | 607 | 568 | dose x route: nasal vs parenteral | incidence-rate ratio | 1.35 (1.03 to 1.76) | 0.0306 |
| pooled with compound fixed effects | all compounds | dose + route + interaction | 607 | 568 | dose x route: oral vs parenteral | incidence-rate ratio | 1.04 (0.79 to 1.37) | 0.7798 |
| pooled with compound fixed effects | all compounds | dose + route + interaction | 607 | 568 | compound: 4'-DMA vs BPC-157 | incidence-rate ratio | 4.32 (1.35 to 13.78) | 0.0135 |
| pooled with compound fixed effects | all compounds | dose + route + interaction | 607 | 568 | compound: 7,8-DHF vs BPC-157 | incidence-rate ratio | 3.14 (0.80 to 12.29) | 0.0998 |
| pooled with compound fixed effects | all compounds | dose + route + interaction | 607 | 568 | compound: 9-MBC vs BPC-157 | incidence-rate ratio | 1.6e-10 (1.5e-11 to 1.6e-09) | <0.0001 |
| pooled with compound fixed effects | all compounds | dose + route + interaction | 607 | 568 | compound: Cerebrolysin vs BPC-157 | incidence-rate ratio | 1.6e-10 (3.2e-11 to 8.2e-10) | <0.0001 |
| pooled with compound fixed effects | all compounds | dose + route + interaction | 607 | 568 | compound: Dihexa vs BPC-157 | incidence-rate ratio | 2.05 (0.67 to 6.31) | 0.2114 |
| pooled with compound fixed effects | all compounds | dose + route + interaction | 607 | 568 | compound: Lion's mane vs BPC-157 | incidence-rate ratio | 8.86 (0.69 to 113.28) | 0.0933 |
| pooled with compound fixed effects | all compounds | dose + route + interaction | 607 | 568 | compound: NSI-189 vs BPC-157 | incidence-rate ratio | 3.16 (0.86 to 11.62) | 0.0832 |
| pooled with compound fixed effects | all compounds | dose + route + interaction | 607 | 568 | compound: Selank vs BPC-157 | incidence-rate ratio | 0.58 (0.38 to 0.91) | 0.0169 |
| pooled with compound fixed effects | all compounds | dose + route + interaction | 607 | 568 | compound: Semax vs BPC-157 | incidence-rate ratio | 0.87 (0.59 to 1.30) | 0.5094 |

## side-effect-level ordinal severity

| Scope | Compound | Model | Observations | Author clusters | Term | Scale | Estimate (95% CI) | p |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| treatment-specific | BPC-157 | dose only | 79 | 65 | log2 dose (per doubling) | odds ratio | 1.30 (0.82 to 2.07) | 0.2692 |
| treatment-specific | BPC-157 | dose only | 79 | 65 | safety domain: activation or anxiety vs other | odds ratio | 0.82 (0.22 to 3.01) | 0.7671 |
| treatment-specific | BPC-157 | dose only | 79 | 65 | safety domain: fatigue or sedation vs other | odds ratio | 1.77 (0.36 to 8.57) | 0.4801 |
| treatment-specific | BPC-157 | dose only | 79 | 65 | safety domain: mood vs other | odds ratio | 2.00 (0.35 to 11.55) | 0.4367 |
| treatment-specific | BPC-157 | dose only | 79 | 65 | safety domain: neurologic vs other | odds ratio | 0.24 (0.05 to 1.05) | 0.0575 |
| treatment-specific | BPC-157 | dose only | 79 | 65 | safety domain: other or rare vs other | odds ratio | 2.81 (0.79 to 10.03) | 0.1124 |
| treatment-specific | Lion's mane | dose only | 27 | 23 | log2 dose (per doubling) | odds ratio | 0.48 (0.22 to 1.07) | 0.0712 |
| treatment-specific | Lion's mane | dose only | 27 | 23 | safety domain: neurologic vs other or rare | odds ratio | 0.37 (0.05 to 2.53) | 0.3090 |
| treatment-specific | Lion's mane | dose only | 27 | 23 | safety domain: other vs other or rare | odds ratio | 0.47 (0.07 to 3.17) | 0.4358 |
| pooled with compound and safety-domain fixed effects | all compounds | dose only | 137 | 109 | log2 dose (per doubling) | odds ratio | 0.98 (0.66 to 1.45) | 0.9107 |
| pooled with compound and safety-domain fixed effects | all compounds | dose only | 137 | 109 | compound: Lion's mane vs BPC-157 | odds ratio | 1.19 (0.01 to 128.07) | 0.9406 |
| pooled with compound and safety-domain fixed effects | all compounds | dose only | 137 | 109 | compound: NSI-189 vs BPC-157 | odds ratio | 0.41 (0.02 to 9.20) | 0.5770 |
| pooled with compound and safety-domain fixed effects | all compounds | dose only | 137 | 109 | compound: Selank vs BPC-157 | odds ratio | 0.49 (0.05 to 4.59) | 0.5284 |
| pooled with compound and safety-domain fixed effects | all compounds | dose only | 137 | 109 | compound: Semax vs BPC-157 | odds ratio | 0.24 (0.05 to 1.14) | 0.0721 |
| pooled with compound and safety-domain fixed effects | all compounds | dose only | 137 | 109 | safety domain: activation or anxiety vs other | odds ratio | 0.76 (0.30 to 1.93) | 0.5600 |
| pooled with compound and safety-domain fixed effects | all compounds | dose only | 137 | 109 | safety domain: cardiovascular or autonomic vs other | odds ratio | 1.56 (0.28 to 8.69) | 0.6121 |
| pooled with compound and safety-domain fixed effects | all compounds | dose only | 137 | 109 | safety domain: fatigue or sedation vs other | odds ratio | 1.97 (0.46 to 8.40) | 0.3610 |
| pooled with compound and safety-domain fixed effects | all compounds | dose only | 137 | 109 | safety domain: gastrointestinal vs other | odds ratio | 0.46 (0.10 to 2.22) | 0.3354 |
| pooled with compound and safety-domain fixed effects | all compounds | dose only | 137 | 109 | safety domain: mood vs other | odds ratio | 2.68 (0.60 to 11.95) | 0.1954 |
| pooled with compound and safety-domain fixed effects | all compounds | dose only | 137 | 109 | safety domain: neurologic vs other | odds ratio | 0.45 (0.15 to 1.35) | 0.1529 |
| pooled with compound and safety-domain fixed effects | all compounds | dose only | 137 | 109 | safety domain: other or rare vs other | odds ratio | 360435324348.77 (71859229897.11 to 1807890555248.19) | <0.0001 |
| pooled with compound and safety-domain fixed effects | all compounds | dose only | 137 | 109 | safety domain: sleep vs other | odds ratio | 2.72 (0.71 to 10.51) | 0.1457 |
| treatment-specific | BPC-157 | route only | 100 | 84 | route: oral vs parenteral | odds ratio | 1.58 (0.57 to 4.36) | 0.3813 |
| treatment-specific | BPC-157 | route only | 100 | 84 | safety domain: activation or anxiety vs other | odds ratio | 0.62 (0.16 to 2.37) | 0.4880 |
| treatment-specific | BPC-157 | route only | 100 | 84 | safety domain: fatigue or sedation vs other | odds ratio | 0.32 (0.09 to 1.18) | 0.0871 |
| treatment-specific | BPC-157 | route only | 100 | 84 | safety domain: gastrointestinal vs other | odds ratio | 0.18 (0.04 to 0.84) | 0.0291 |
| treatment-specific | BPC-157 | route only | 100 | 84 | safety domain: mood vs other | odds ratio | 0.95 (0.23 to 3.85) | 0.9390 |
| treatment-specific | BPC-157 | route only | 100 | 84 | safety domain: neurologic vs other | odds ratio | 0.11 (0.02 to 0.50) | 0.0048 |
| treatment-specific | BPC-157 | route only | 100 | 84 | safety domain: other or rare vs other | odds ratio | 0.57 (0.12 to 2.72) | 0.4832 |
| pooled with compound and safety-domain fixed effects | all compounds | route only | 136 | 110 | route: nasal vs parenteral | odds ratio | 0.91 (0.24 to 3.46) | 0.8958 |
| pooled with compound and safety-domain fixed effects | all compounds | route only | 136 | 110 | route: oral vs parenteral | odds ratio | 1.81 (0.65 to 5.06) | 0.2579 |
| pooled with compound and safety-domain fixed effects | all compounds | route only | 136 | 110 | compound: 7,8-DHF vs BPC-157 | odds ratio | 0.94 (0.08 to 11.69) | 0.9601 |
| pooled with compound and safety-domain fixed effects | all compounds | route only | 136 | 110 | compound: NSI-189 vs BPC-157 | odds ratio | 0.20 (0.04 to 0.95) | 0.0430 |
| pooled with compound and safety-domain fixed effects | all compounds | route only | 136 | 110 | compound: Selank vs BPC-157 | odds ratio | 0.37 (0.04 to 3.46) | 0.3814 |
| pooled with compound and safety-domain fixed effects | all compounds | route only | 136 | 110 | compound: Semax vs BPC-157 | odds ratio | 0.33 (0.08 to 1.37) | 0.1270 |
| pooled with compound and safety-domain fixed effects | all compounds | route only | 136 | 110 | safety domain: activation or anxiety vs other | odds ratio | 0.35 (0.13 to 0.94) | 0.0381 |
| pooled with compound and safety-domain fixed effects | all compounds | route only | 136 | 110 | safety domain: fatigue or sedation vs other | odds ratio | 0.37 (0.10 to 1.31) | 0.1222 |
| pooled with compound and safety-domain fixed effects | all compounds | route only | 136 | 110 | safety domain: gastrointestinal vs other | odds ratio | 0.16 (0.04 to 0.77) | 0.0218 |
| pooled with compound and safety-domain fixed effects | all compounds | route only | 136 | 110 | safety domain: mood vs other | odds ratio | 1.25 (0.30 to 5.24) | 0.7604 |
| pooled with compound and safety-domain fixed effects | all compounds | route only | 136 | 110 | safety domain: neurologic vs other | odds ratio | 0.10 (0.03 to 0.40) | 0.0011 |
| pooled with compound and safety-domain fixed effects | all compounds | route only | 136 | 110 | safety domain: other or rare vs other | odds ratio | 1.53 (0.24 to 9.82) | 0.6510 |
| pooled with compound and safety-domain fixed effects | all compounds | route only | 136 | 110 | safety domain: sleep vs other | odds ratio | 0.61 (0.08 to 4.49) | 0.6304 |
| treatment-specific | BPC-157 | dose + route | 37 | 33 | log2 dose (per doubling) | odds ratio | 0.47 (0.21 to 1.05) | 0.0651 |
| treatment-specific | BPC-157 | dose + route | 37 | 33 | route: oral vs parenteral | odds ratio | 0.76 (0.17 to 3.34) | 0.7158 |
| treatment-specific | BPC-157 | dose + route | 37 | 33 | safety domain: activation or anxiety vs other | odds ratio | 0.22 (0.02 to 2.05) | 0.1823 |
| treatment-specific | BPC-157 | dose + route | 37 | 33 | safety domain: fatigue or sedation vs other | odds ratio | 1.21 (0.22 to 6.62) | 0.8231 |
| treatment-specific | BPC-157 | dose + route | 37 | 33 | safety domain: other or rare vs other | odds ratio | 0.95 (0.19 to 4.78) | 0.9521 |
| treatment-specific | BPC-157 | dose + route + interaction | 37 | 33 | log2 dose (per doubling) | odds ratio | 0.67 (0.28 to 1.61) | 0.3743 |
| treatment-specific | BPC-157 | dose + route + interaction | 37 | 33 | route: oral vs parenteral | odds ratio | 0.04 (0.00042 to 4.03) | 0.1728 |
| treatment-specific | BPC-157 | dose + route + interaction | 37 | 33 | dose x route: oral vs parenteral | odds ratio | 0.11 (0.01 to 1.86) | 0.1253 |
| treatment-specific | BPC-157 | dose + route + interaction | 37 | 33 | safety domain: activation or anxiety vs other | odds ratio | 0.31 (0.03 to 3.05) | 0.3172 |
| treatment-specific | BPC-157 | dose + route + interaction | 37 | 33 | safety domain: fatigue or sedation vs other | odds ratio | 2.09 (0.27 to 16.54) | 0.4833 |
| treatment-specific | BPC-157 | dose + route + interaction | 37 | 33 | safety domain: other or rare vs other | odds ratio | 0.93 (0.19 to 4.48) | 0.9242 |

## maximum severity

| Scope | Compound | Model | Observations | Author clusters | Term | Scale | Estimate (95% CI) | p |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| treatment-specific | BPC-157 | dose only | 65 | 65 | intercept | severity-score difference | 2.42 (1.99 to 2.85) | <0.0001 |
| treatment-specific | BPC-157 | dose only | 65 | 65 | log2 dose (per doubling) | severity-score difference | 0.05 (-0.20 to 0.30) | 0.6799 |
| treatment-specific | Lion's mane | dose only | 23 | 23 | intercept | severity-score difference | 4.60 (0.69 to 8.52) | 0.0233 |
| treatment-specific | Lion's mane | dose only | 23 | 23 | log2 dose (per doubling) | severity-score difference | -0.25 (-0.65 to 0.15) | 0.2007 |
| pooled with compound fixed effects | all compounds | dose only | 118 | 114 | intercept | severity-score difference | 2.40 (2.06 to 2.74) | <0.0001 |
| pooled with compound fixed effects | all compounds | dose only | 118 | 114 | log2 dose (per doubling) | severity-score difference | 0.04 (-0.14 to 0.21) | 0.6638 |
| pooled with compound fixed effects | all compounds | dose only | 118 | 114 | compound: 4'-DMA vs BPC-157 | severity-score difference | -1.58 (-2.69 to -0.47) | 0.0056 |
| pooled with compound fixed effects | all compounds | dose only | 118 | 114 | compound: 7,8-DHF vs BPC-157 | severity-score difference | -0.55 (-2.32 to 1.21) | 0.5364 |
| pooled with compound fixed effects | all compounds | dose only | 118 | 114 | compound: Dihexa vs BPC-157 | severity-score difference | -1.54 (-2.45 to -0.62) | 0.0012 |
| pooled with compound fixed effects | all compounds | dose only | 118 | 114 | compound: Lion's mane vs BPC-157 | severity-score difference | -0.69 (-2.75 to 1.37) | 0.5077 |
| pooled with compound fixed effects | all compounds | dose only | 118 | 114 | compound: NSI-189 vs BPC-157 | severity-score difference | -0.78 (-2.04 to 0.49) | 0.2260 |
| pooled with compound fixed effects | all compounds | dose only | 118 | 114 | compound: Selank vs BPC-157 | severity-score difference | -0.12 (-1.05 to 0.82) | 0.8026 |
| pooled with compound fixed effects | all compounds | dose only | 118 | 114 | compound: Semax vs BPC-157 | severity-score difference | -0.55 (-1.22 to 0.12) | 0.1080 |
| treatment-specific | BPC-157 | route only | 84 | 84 | intercept | severity-score difference | 2.33 (2.09 to 2.58) | <0.0001 |
| treatment-specific | BPC-157 | route only | 84 | 84 | route: oral vs parenteral | severity-score difference | 0.11 (-0.30 to 0.52) | 0.5941 |
| pooled with compound fixed effects | all compounds | route only | 117 | 115 | intercept | severity-score difference | 2.36 (2.11 to 2.61) | <0.0001 |
| pooled with compound fixed effects | all compounds | route only | 117 | 115 | route: nasal vs parenteral | severity-score difference | 0.16 (-0.50 to 0.82) | 0.6362 |
| pooled with compound fixed effects | all compounds | route only | 117 | 115 | route: oral vs parenteral | severity-score difference | 0.08 (-0.33 to 0.49) | 0.6987 |
| pooled with compound fixed effects | all compounds | route only | 117 | 115 | compound: 4'-DMA vs BPC-157 | severity-score difference | -1.44 (-1.77 to -1.11) | <0.0001 |
| pooled with compound fixed effects | all compounds | route only | 117 | 115 | compound: 7,8-DHF vs BPC-157 | severity-score difference | -0.44 (-1.53 to 0.65) | 0.4252 |
| pooled with compound fixed effects | all compounds | route only | 117 | 115 | compound: 9-MBC vs BPC-157 | severity-score difference | -1.44 (-1.77 to -1.11) | <0.0001 |
| pooled with compound fixed effects | all compounds | route only | 117 | 115 | compound: Cerebrolysin vs BPC-157 | severity-score difference | 0.64 (0.39 to 0.89) | <0.0001 |
| pooled with compound fixed effects | all compounds | route only | 117 | 115 | compound: Dihexa vs BPC-157 | severity-score difference | -0.48 (-1.94 to 0.98) | 0.5167 |
| pooled with compound fixed effects | all compounds | route only | 117 | 115 | compound: NSI-189 vs BPC-157 | severity-score difference | -0.66 (-1.63 to 0.31) | 0.1833 |
| pooled with compound fixed effects | all compounds | route only | 117 | 115 | compound: Selank vs BPC-157 | severity-score difference | -0.47 (-1.41 to 0.48) | 0.3299 |
| pooled with compound fixed effects | all compounds | route only | 117 | 115 | compound: Semax vs BPC-157 | severity-score difference | -0.47 (-1.28 to 0.34) | 0.2497 |
| treatment-specific | BPC-157 | dose + route | 33 | 33 | intercept | severity-score difference | 1.93 (1.10 to 2.76) | <0.0001 |
| treatment-specific | BPC-157 | dose + route | 33 | 33 | log2 dose (per doubling) | severity-score difference | -0.29 (-0.71 to 0.13) | 0.1741 |
| treatment-specific | BPC-157 | dose + route | 33 | 33 | route: oral vs parenteral | severity-score difference | -0.09 (-0.83 to 0.65) | 0.8036 |
| pooled with compound fixed effects | all compounds | dose + route | 40 | 40 | intercept | severity-score difference | 1.98 (1.16 to 2.81) | <0.0001 |
| pooled with compound fixed effects | all compounds | dose + route | 40 | 40 | log2 dose (per doubling) | severity-score difference | -0.26 (-0.67 to 0.16) | 0.2222 |
| pooled with compound fixed effects | all compounds | dose + route | 40 | 40 | route: oral vs parenteral | severity-score difference | -0.10 (-0.84 to 0.63) | 0.7798 |
| pooled with compound fixed effects | all compounds | dose + route | 40 | 40 | compound: 4'-DMA vs BPC-157 | severity-score difference | 0.35 (-2.34 to 3.03) | 0.7959 |
| pooled with compound fixed effects | all compounds | dose + route | 40 | 40 | compound: 7,8-DHF vs BPC-157 | severity-score difference | 1.16 (-1.68 to 3.99) | 0.4147 |
| pooled with compound fixed effects | all compounds | dose + route | 40 | 40 | compound: Dihexa vs BPC-157 | severity-score difference | -0.29 (-1.98 to 1.41) | 0.7334 |
| pooled with compound fixed effects | all compounds | dose + route | 40 | 40 | compound: NSI-189 vs BPC-157 | severity-score difference | 1.47 (-1.90 to 4.83) | 0.3833 |
| pooled with compound fixed effects | all compounds | dose + route | 40 | 40 | compound: Selank vs BPC-157 | severity-score difference | -1.32 (-1.74 to -0.90) | <0.0001 |
| treatment-specific | BPC-157 | dose + route + interaction | 33 | 33 | intercept | severity-score difference | 2.23 (1.19 to 3.27) | 0.0001 |
| treatment-specific | BPC-157 | dose + route + interaction | 33 | 33 | log2 dose (per doubling) | severity-score difference | -0.11 (-0.65 to 0.44) | 0.6857 |
| treatment-specific | BPC-157 | dose + route + interaction | 33 | 33 | route: oral vs parenteral | severity-score difference | -1.07 (-3.52 to 1.37) | 0.3769 |
| treatment-specific | BPC-157 | dose + route + interaction | 33 | 33 | dose x route: oral vs parenteral | severity-score difference | -0.69 (-2.04 to 0.66) | 0.3071 |
| pooled with compound fixed effects | all compounds | dose + route + interaction | 40 | 40 | intercept | severity-score difference | 2.23 (1.21 to 3.25) | <0.0001 |
| pooled with compound fixed effects | all compounds | dose + route + interaction | 40 | 40 | log2 dose (per doubling) | severity-score difference | -0.11 (-0.64 to 0.42) | 0.6808 |
| pooled with compound fixed effects | all compounds | dose + route + interaction | 40 | 40 | route: oral vs parenteral | severity-score difference | -0.87 (-2.53 to 0.79) | 0.2943 |
| pooled with compound fixed effects | all compounds | dose + route + interaction | 40 | 40 | dose x route: oral vs parenteral | severity-score difference | -0.53 (-1.40 to 0.33) | 0.2172 |
| pooled with compound fixed effects | all compounds | dose + route + interaction | 40 | 40 | compound: 4'-DMA vs BPC-157 | severity-score difference | 2.73 (-1.77 to 7.23) | 0.2277 |
| pooled with compound fixed effects | all compounds | dose + route + interaction | 40 | 40 | compound: 7,8-DHF vs BPC-157 | severity-score difference | 3.25 (-1.01 to 7.51) | 0.1311 |
| pooled with compound fixed effects | all compounds | dose + route + interaction | 40 | 40 | compound: Dihexa vs BPC-157 | severity-score difference | 1.13 (-1.70 to 3.97) | 0.4232 |
| pooled with compound fixed effects | all compounds | dose + route + interaction | 40 | 40 | compound: NSI-189 vs BPC-157 | severity-score difference | 4.03 (-1.19 to 9.26) | 0.1264 |
| pooled with compound fixed effects | all compounds | dose + route + interaction | 40 | 40 | compound: Selank vs BPC-157 | severity-score difference | -1.38 (-1.83 to -0.93) | <0.0001 |

## average severity

| Scope | Compound | Model | Observations | Author clusters | Term | Scale | Estimate (95% CI) | p |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| treatment-specific | BPC-157 | dose only | 65 | 65 | intercept | severity-score difference | 2.44 (2.03 to 2.85) | <0.0001 |
| treatment-specific | BPC-157 | dose only | 65 | 65 | log2 dose (per doubling) | severity-score difference | 0.10 (-0.13 to 0.33) | 0.3934 |
| treatment-specific | Lion's mane | dose only | 23 | 23 | intercept | severity-score difference | 4.60 (0.69 to 8.52) | 0.0233 |
| treatment-specific | Lion's mane | dose only | 23 | 23 | log2 dose (per doubling) | severity-score difference | -0.25 (-0.65 to 0.15) | 0.2007 |
| pooled with compound fixed effects | all compounds | dose only | 118 | 114 | intercept | severity-score difference | 2.38 (2.04 to 2.71) | <0.0001 |
| pooled with compound fixed effects | all compounds | dose only | 118 | 114 | log2 dose (per doubling) | severity-score difference | 0.06 (-0.11 to 0.22) | 0.5008 |
| pooled with compound fixed effects | all compounds | dose only | 118 | 114 | compound: 4'-DMA vs BPC-157 | severity-score difference | -1.65 (-2.73 to -0.57) | 0.0031 |
| pooled with compound fixed effects | all compounds | dose only | 118 | 114 | compound: 7,8-DHF vs BPC-157 | severity-score difference | -0.61 (-2.36 to 1.15) | 0.4950 |
| pooled with compound fixed effects | all compounds | dose only | 118 | 114 | compound: Dihexa vs BPC-157 | severity-score difference | -1.58 (-2.47 to -0.69) | 0.0006 |
| pooled with compound fixed effects | all compounds | dose only | 118 | 114 | compound: Lion's mane vs BPC-157 | severity-score difference | -0.85 (-2.85 to 1.15) | 0.3991 |
| pooled with compound fixed effects | all compounds | dose only | 118 | 114 | compound: NSI-189 vs BPC-157 | severity-score difference | -0.91 (-2.15 to 0.33) | 0.1474 |
| pooled with compound fixed effects | all compounds | dose only | 118 | 114 | compound: Selank vs BPC-157 | severity-score difference | -0.06 (-0.98 to 0.87) | 0.9063 |
| pooled with compound fixed effects | all compounds | dose only | 118 | 114 | compound: Semax vs BPC-157 | severity-score difference | -0.50 (-1.16 to 0.17) | 0.1406 |
| treatment-specific | BPC-157 | route only | 84 | 84 | intercept | severity-score difference | 2.29 (2.04 to 2.53) | <0.0001 |
| treatment-specific | BPC-157 | route only | 84 | 84 | route: oral vs parenteral | severity-score difference | 0.16 (-0.25 to 0.57) | 0.4464 |
| pooled with compound fixed effects | all compounds | route only | 117 | 115 | intercept | severity-score difference | 2.31 (2.07 to 2.56) | <0.0001 |
| pooled with compound fixed effects | all compounds | route only | 117 | 115 | route: nasal vs parenteral | severity-score difference | 0.25 (-0.36 to 0.87) | 0.4153 |
| pooled with compound fixed effects | all compounds | route only | 117 | 115 | route: oral vs parenteral | severity-score difference | 0.13 (-0.28 to 0.53) | 0.5404 |
| pooled with compound fixed effects | all compounds | route only | 117 | 115 | compound: 4'-DMA vs BPC-157 | severity-score difference | -1.44 (-1.76 to -1.11) | <0.0001 |
| pooled with compound fixed effects | all compounds | route only | 117 | 115 | compound: 7,8-DHF vs BPC-157 | severity-score difference | -0.44 (-1.53 to 0.65) | 0.4277 |
| pooled with compound fixed effects | all compounds | route only | 117 | 115 | compound: 9-MBC vs BPC-157 | severity-score difference | -1.44 (-1.76 to -1.11) | <0.0001 |
| pooled with compound fixed effects | all compounds | route only | 117 | 115 | compound: Cerebrolysin vs BPC-157 | severity-score difference | 0.69 (0.44 to 0.93) | <0.0001 |
| pooled with compound fixed effects | all compounds | route only | 117 | 115 | compound: Dihexa vs BPC-157 | severity-score difference | -0.50 (-1.92 to 0.92) | 0.4854 |
| pooled with compound fixed effects | all compounds | route only | 117 | 115 | compound: NSI-189 vs BPC-157 | severity-score difference | -0.80 (-1.65 to 0.06) | 0.0680 |
| pooled with compound fixed effects | all compounds | route only | 117 | 115 | compound: Selank vs BPC-157 | severity-score difference | -0.48 (-1.41 to 0.45) | 0.3084 |
| pooled with compound fixed effects | all compounds | route only | 117 | 115 | compound: Semax vs BPC-157 | severity-score difference | -0.69 (-1.40 to 0.02) | 0.0580 |
| treatment-specific | BPC-157 | dose + route | 33 | 33 | intercept | severity-score difference | 1.97 (1.12 to 2.82) | <0.0001 |
| treatment-specific | BPC-157 | dose + route | 33 | 33 | log2 dose (per doubling) | severity-score difference | -0.23 (-0.66 to 0.19) | 0.2716 |
| treatment-specific | BPC-157 | dose + route | 33 | 33 | route: oral vs parenteral | severity-score difference | -0.06 (-0.82 to 0.70) | 0.8701 |
| pooled with compound fixed effects | all compounds | dose + route | 40 | 40 | intercept | severity-score difference | 2.00 (1.16 to 2.84) | <0.0001 |
| pooled with compound fixed effects | all compounds | dose + route | 40 | 40 | log2 dose (per doubling) | severity-score difference | -0.22 (-0.64 to 0.20) | 0.2949 |
| pooled with compound fixed effects | all compounds | dose + route | 40 | 40 | route: oral vs parenteral | severity-score difference | -0.07 (-0.82 to 0.68) | 0.8574 |
| pooled with compound fixed effects | all compounds | dose + route | 40 | 40 | compound: 4'-DMA vs BPC-157 | severity-score difference | 0.12 (-2.56 to 2.80) | 0.9283 |
| pooled with compound fixed effects | all compounds | dose + route | 40 | 40 | compound: 7,8-DHF vs BPC-157 | severity-score difference | 0.96 (-1.88 to 3.79) | 0.4989 |
| pooled with compound fixed effects | all compounds | dose + route | 40 | 40 | compound: Dihexa vs BPC-157 | severity-score difference | -0.42 (-2.11 to 1.27) | 0.6172 |
| pooled with compound fixed effects | all compounds | dose + route | 40 | 40 | compound: NSI-189 vs BPC-157 | severity-score difference | 0.89 (-2.22 to 4.00) | 0.5657 |
| pooled with compound fixed effects | all compounds | dose + route | 40 | 40 | compound: Selank vs BPC-157 | severity-score difference | -1.29 (-1.71 to -0.86) | <0.0001 |
| treatment-specific | BPC-157 | dose + route + interaction | 33 | 33 | intercept | severity-score difference | 2.30 (1.27 to 3.34) | <0.0001 |
| treatment-specific | BPC-157 | dose + route + interaction | 33 | 33 | log2 dose (per doubling) | severity-score difference | -0.04 (-0.56 to 0.48) | 0.8819 |
| treatment-specific | BPC-157 | dose + route + interaction | 33 | 33 | route: oral vs parenteral | severity-score difference | -1.15 (-3.59 to 1.30) | 0.3456 |
| treatment-specific | BPC-157 | dose + route + interaction | 33 | 33 | dose x route: oral vs parenteral | severity-score difference | -0.76 (-2.10 to 0.58) | 0.2572 |
| pooled with compound fixed effects | all compounds | dose + route + interaction | 40 | 40 | intercept | severity-score difference | 2.30 (1.28 to 3.32) | <0.0001 |
| pooled with compound fixed effects | all compounds | dose + route + interaction | 40 | 40 | log2 dose (per doubling) | severity-score difference | -0.04 (-0.55 to 0.47) | 0.8816 |
| pooled with compound fixed effects | all compounds | dose + route + interaction | 40 | 40 | route: oral vs parenteral | severity-score difference | -1.02 (-2.68 to 0.65) | 0.2250 |
| pooled with compound fixed effects | all compounds | dose + route + interaction | 40 | 40 | dose x route: oral vs parenteral | severity-score difference | -0.66 (-1.50 to 0.18) | 0.1216 |
| pooled with compound fixed effects | all compounds | dose + route + interaction | 40 | 40 | compound: 4'-DMA vs BPC-157 | severity-score difference | 3.06 (-1.41 to 7.53) | 0.1744 |
| pooled with compound fixed effects | all compounds | dose + route + interaction | 40 | 40 | compound: 7,8-DHF vs BPC-157 | severity-score difference | 3.54 (-0.70 to 7.77) | 0.0989 |
| pooled with compound fixed effects | all compounds | dose + route + interaction | 40 | 40 | compound: Dihexa vs BPC-157 | severity-score difference | 1.33 (-1.50 to 4.16) | 0.3469 |
| pooled with compound fixed effects | all compounds | dose + route + interaction | 40 | 40 | compound: NSI-189 vs BPC-157 | severity-score difference | 4.06 (-0.96 to 9.08) | 0.1100 |
| pooled with compound fixed effects | all compounds | dose + route + interaction | 40 | 40 | compound: Selank vs BPC-157 | severity-score difference | -1.35 (-1.82 to -0.89) | <0.0001 |

## Maximum-severity primary and dose-screen sensitivity coefficients

| Analysis set | Scope | Compound | Model | Authors | Term | Score difference (95% CI) | p |
| --- | --- | --- | --- | --- | --- | --- | --- |
| primary | treatment-specific | BPC-157 | dose only | 65 | intercept | 2.42 (1.99 to 2.85) | <0.0001 |
| primary | treatment-specific | BPC-157 | dose only | 65 | log2 dose (per doubling) | 0.05 (-0.20 to 0.30) | 0.6799 |
| primary | treatment-specific | Lion's mane | dose only | 23 | intercept | 4.60 (0.69 to 8.52) | 0.0233 |
| primary | treatment-specific | Lion's mane | dose only | 23 | log2 dose (per doubling) | -0.25 (-0.65 to 0.15) | 0.2007 |
| primary | pooled with compound fixed effects | all compounds | dose only | 118 | intercept | 2.40 (2.06 to 2.74) | <0.0001 |
| primary | pooled with compound fixed effects | all compounds | dose only | 118 | log2 dose (per doubling) | 0.04 (-0.14 to 0.21) | 0.6638 |
| primary | pooled with compound fixed effects | all compounds | dose only | 118 | compound: 4'-DMA vs BPC-157 | -1.58 (-2.69 to -0.47) | 0.0056 |
| primary | pooled with compound fixed effects | all compounds | dose only | 118 | compound: 7,8-DHF vs BPC-157 | -0.55 (-2.32 to 1.21) | 0.5364 |
| primary | pooled with compound fixed effects | all compounds | dose only | 118 | compound: Dihexa vs BPC-157 | -1.54 (-2.45 to -0.62) | 0.0012 |
| primary | pooled with compound fixed effects | all compounds | dose only | 118 | compound: Lion's mane vs BPC-157 | -0.69 (-2.75 to 1.37) | 0.5077 |
| primary | pooled with compound fixed effects | all compounds | dose only | 118 | compound: NSI-189 vs BPC-157 | -0.78 (-2.04 to 0.49) | 0.2260 |
| primary | pooled with compound fixed effects | all compounds | dose only | 118 | compound: Selank vs BPC-157 | -0.12 (-1.05 to 0.82) | 0.8026 |
| primary | pooled with compound fixed effects | all compounds | dose only | 118 | compound: Semax vs BPC-157 | -0.55 (-1.22 to 0.12) | 0.1080 |
| primary | treatment-specific | BPC-157 | route only | 84 | intercept | 2.33 (2.09 to 2.58) | <0.0001 |
| primary | treatment-specific | BPC-157 | route only | 84 | route: oral vs parenteral | 0.11 (-0.30 to 0.52) | 0.5941 |
| primary | pooled with compound fixed effects | all compounds | route only | 117 | intercept | 2.36 (2.11 to 2.61) | <0.0001 |
| primary | pooled with compound fixed effects | all compounds | route only | 117 | route: nasal vs parenteral | 0.16 (-0.50 to 0.82) | 0.6362 |
| primary | pooled with compound fixed effects | all compounds | route only | 117 | route: oral vs parenteral | 0.08 (-0.33 to 0.49) | 0.6987 |
| primary | pooled with compound fixed effects | all compounds | route only | 117 | compound: 4'-DMA vs BPC-157 | -1.44 (-1.77 to -1.11) | <0.0001 |
| primary | pooled with compound fixed effects | all compounds | route only | 117 | compound: 7,8-DHF vs BPC-157 | -0.44 (-1.53 to 0.65) | 0.4252 |
| primary | pooled with compound fixed effects | all compounds | route only | 117 | compound: 9-MBC vs BPC-157 | -1.44 (-1.77 to -1.11) | <0.0001 |
| primary | pooled with compound fixed effects | all compounds | route only | 117 | compound: Cerebrolysin vs BPC-157 | 0.64 (0.39 to 0.89) | <0.0001 |
| primary | pooled with compound fixed effects | all compounds | route only | 117 | compound: Dihexa vs BPC-157 | -0.48 (-1.94 to 0.98) | 0.5167 |
| primary | pooled with compound fixed effects | all compounds | route only | 117 | compound: NSI-189 vs BPC-157 | -0.66 (-1.63 to 0.31) | 0.1833 |
| primary | pooled with compound fixed effects | all compounds | route only | 117 | compound: Selank vs BPC-157 | -0.47 (-1.41 to 0.48) | 0.3299 |
| primary | pooled with compound fixed effects | all compounds | route only | 117 | compound: Semax vs BPC-157 | -0.47 (-1.28 to 0.34) | 0.2497 |
| primary | treatment-specific | BPC-157 | dose + route | 33 | intercept | 1.93 (1.10 to 2.76) | <0.0001 |
| primary | treatment-specific | BPC-157 | dose + route | 33 | log2 dose (per doubling) | -0.29 (-0.71 to 0.13) | 0.1741 |
| primary | treatment-specific | BPC-157 | dose + route | 33 | route: oral vs parenteral | -0.09 (-0.83 to 0.65) | 0.8036 |
| primary | pooled with compound fixed effects | all compounds | dose + route | 40 | intercept | 1.98 (1.16 to 2.81) | <0.0001 |
| primary | pooled with compound fixed effects | all compounds | dose + route | 40 | log2 dose (per doubling) | -0.26 (-0.67 to 0.16) | 0.2222 |
| primary | pooled with compound fixed effects | all compounds | dose + route | 40 | route: oral vs parenteral | -0.10 (-0.84 to 0.63) | 0.7798 |
| primary | pooled with compound fixed effects | all compounds | dose + route | 40 | compound: 4'-DMA vs BPC-157 | 0.35 (-2.34 to 3.03) | 0.7959 |
| primary | pooled with compound fixed effects | all compounds | dose + route | 40 | compound: 7,8-DHF vs BPC-157 | 1.16 (-1.68 to 3.99) | 0.4147 |
| primary | pooled with compound fixed effects | all compounds | dose + route | 40 | compound: Dihexa vs BPC-157 | -0.29 (-1.98 to 1.41) | 0.7334 |
| primary | pooled with compound fixed effects | all compounds | dose + route | 40 | compound: NSI-189 vs BPC-157 | 1.47 (-1.90 to 4.83) | 0.3833 |
| primary | pooled with compound fixed effects | all compounds | dose + route | 40 | compound: Selank vs BPC-157 | -1.32 (-1.74 to -0.90) | <0.0001 |
| all linked doses | treatment-specific | BPC-157 | dose only | 76 | intercept | 2.21 (2.00 to 2.42) | <0.0001 |
| all linked doses | treatment-specific | BPC-157 | dose only | 76 | log2 dose (per doubling) | -0.08 (-0.15 to -0.01) | 0.0279 |
| all linked doses | treatment-specific | Lion's mane | dose only | 23 | intercept | 4.60 (0.69 to 8.52) | 0.0233 |
| all linked doses | treatment-specific | Lion's mane | dose only | 23 | log2 dose (per doubling) | -0.25 (-0.65 to 0.15) | 0.2007 |
| all linked doses | pooled with compound fixed effects | all compounds | dose only | 129 | intercept | 2.22 (2.01 to 2.42) | <0.0001 |
| all linked doses | pooled with compound fixed effects | all compounds | dose only | 129 | log2 dose (per doubling) | -0.07 (-0.14 to -0.01) | 0.0272 |
| all linked doses | pooled with compound fixed effects | all compounds | dose only | 129 | compound: 4'-DMA vs BPC-157 | -0.87 (-1.27 to -0.47) | <0.0001 |
| all linked doses | pooled with compound fixed effects | all compounds | dose only | 129 | compound: 7,8-DHF vs BPC-157 | 0.08 (-1.40 to 1.56) | 0.9164 |
| all linked doses | pooled with compound fixed effects | all compounds | dose only | 129 | compound: Dihexa vs BPC-157 | -0.95 (-1.32 to -0.59) | <0.0001 |
| all linked doses | pooled with compound fixed effects | all compounds | dose only | 129 | compound: Lion's mane vs BPC-157 | 0.59 (-0.22 to 1.40) | 0.1502 |
| all linked doses | pooled with compound fixed effects | all compounds | dose only | 129 | compound: NSI-189 vs BPC-157 | -0.07 (-0.84 to 0.69) | 0.8485 |
| all linked doses | pooled with compound fixed effects | all compounds | dose only | 129 | compound: Selank vs BPC-157 | -0.17 (-1.11 to 0.78) | 0.7259 |
| all linked doses | pooled with compound fixed effects | all compounds | dose only | 129 | compound: Semax vs BPC-157 | -0.51 (-1.21 to 0.18) | 0.1450 |
| all linked doses | treatment-specific | BPC-157 | route only | 84 | intercept | 2.33 (2.09 to 2.58) | <0.0001 |
| all linked doses | treatment-specific | BPC-157 | route only | 84 | route: oral vs parenteral | 0.11 (-0.30 to 0.52) | 0.5941 |
| all linked doses | pooled with compound fixed effects | all compounds | route only | 117 | intercept | 2.36 (2.11 to 2.61) | <0.0001 |
| all linked doses | pooled with compound fixed effects | all compounds | route only | 117 | route: nasal vs parenteral | 0.16 (-0.50 to 0.82) | 0.6362 |
| all linked doses | pooled with compound fixed effects | all compounds | route only | 117 | route: oral vs parenteral | 0.08 (-0.33 to 0.49) | 0.6987 |
| all linked doses | pooled with compound fixed effects | all compounds | route only | 117 | compound: 4'-DMA vs BPC-157 | -1.44 (-1.77 to -1.11) | <0.0001 |
| all linked doses | pooled with compound fixed effects | all compounds | route only | 117 | compound: 7,8-DHF vs BPC-157 | -0.44 (-1.53 to 0.65) | 0.4252 |
| all linked doses | pooled with compound fixed effects | all compounds | route only | 117 | compound: 9-MBC vs BPC-157 | -1.44 (-1.77 to -1.11) | <0.0001 |
| all linked doses | pooled with compound fixed effects | all compounds | route only | 117 | compound: Cerebrolysin vs BPC-157 | 0.64 (0.39 to 0.89) | <0.0001 |
| all linked doses | pooled with compound fixed effects | all compounds | route only | 117 | compound: Dihexa vs BPC-157 | -0.48 (-1.94 to 0.98) | 0.5167 |
| all linked doses | pooled with compound fixed effects | all compounds | route only | 117 | compound: NSI-189 vs BPC-157 | -0.66 (-1.63 to 0.31) | 0.1833 |
| all linked doses | pooled with compound fixed effects | all compounds | route only | 117 | compound: Selank vs BPC-157 | -0.47 (-1.41 to 0.48) | 0.3299 |
| all linked doses | pooled with compound fixed effects | all compounds | route only | 117 | compound: Semax vs BPC-157 | -0.47 (-1.28 to 0.34) | 0.2497 |
| all linked doses | treatment-specific | BPC-157 | dose + route | 37 | intercept | 2.21 (1.86 to 2.55) | <0.0001 |
| all linked doses | treatment-specific | BPC-157 | dose + route | 37 | log2 dose (per doubling) | -0.12 (-0.19 to -0.05) | 0.0016 |
| all linked doses | treatment-specific | BPC-157 | dose + route | 37 | route: oral vs parenteral | -0.02 (-0.72 to 0.68) | 0.9550 |
| all linked doses | pooled with compound fixed effects | all compounds | dose + route | 44 | intercept | 2.21 (1.85 to 2.56) | <0.0001 |
| all linked doses | pooled with compound fixed effects | all compounds | dose + route | 44 | log2 dose (per doubling) | -0.12 (-0.18 to -0.05) | 0.0009 |
| all linked doses | pooled with compound fixed effects | all compounds | dose + route | 44 | route: oral vs parenteral | -0.02 (-0.72 to 0.67) | 0.9470 |
| all linked doses | pooled with compound fixed effects | all compounds | dose + route | 44 | compound: 4'-DMA vs BPC-157 | -0.63 (-1.17 to -0.09) | 0.0238 |
| all linked doses | pooled with compound fixed effects | all compounds | dose + route | 44 | compound: 7,8-DHF vs BPC-157 | 0.28 (-1.35 to 1.92) | 0.7276 |
| all linked doses | pooled with compound fixed effects | all compounds | dose + route | 44 | compound: Dihexa vs BPC-157 | -0.92 (-1.45 to -0.38) | 0.0012 |
| all linked doses | pooled with compound fixed effects | all compounds | dose + route | 44 | compound: NSI-189 vs BPC-157 | 0.43 (-1.31 to 2.16) | 0.6224 |
| all linked doses | pooled with compound fixed effects | all compounds | dose + route | 44 | compound: Selank vs BPC-157 | -1.36 (-1.72 to -1.01) | <0.0001 |

## Fine-grained model statuses

| Outcome | Scope | Compound | Model | Eligible observations | Rare-route exclusions | Status | Reason |
| --- | --- | --- | --- | --- | --- | --- | --- |
| any side effect | treatment-specific | 4'-DMA | dose only | 15 | 0 | not estimable | fewer than 20 observations |
| distinct side-effect count | treatment-specific | 4'-DMA | dose only | 15 | 0 | not estimable | fewer than 20 observations |
| side-effect-level ordinal severity | treatment-specific | 4'-DMA | dose only | 2 | 0 | not estimable | fewer than 20 observations |
| maximum severity | treatment-specific | 4'-DMA | dose only | 1 | 0 | not estimable | fewer than 20 observations |
| average severity | treatment-specific | 4'-DMA | dose only | 1 | 0 | not estimable | fewer than 20 observations |
| any side effect | treatment-specific | 7,8-DHF | dose only | 48 | 0 | fit | GEE with author-clustered robust 95% confidence intervals |
| distinct side-effect count | treatment-specific | 7,8-DHF | dose only | 48 | 0 | fit | GEE with author-clustered robust 95% confidence intervals |
| side-effect-level ordinal severity | treatment-specific | 7,8-DHF | dose only | 3 | 0 | not estimable | fewer than 20 observations |
| maximum severity | treatment-specific | 7,8-DHF | dose only | 2 | 0 | not estimable | fewer than 20 observations |
| average severity | treatment-specific | 7,8-DHF | dose only | 2 | 0 | not estimable | fewer than 20 observations |
| any side effect | treatment-specific | 9-MBC | dose only | 8 | 0 | not estimable | fewer than 20 observations |
| distinct side-effect count | treatment-specific | 9-MBC | dose only | 8 | 0 | not estimable | fewer than 20 observations |
| side-effect-level ordinal severity | treatment-specific | 9-MBC | dose only | 0 | 0 | not estimable | fewer than 20 observations |
| maximum severity | treatment-specific | 9-MBC | dose only | 0 | 0 | not estimable | fewer than 20 observations |
| average severity | treatment-specific | 9-MBC | dose only | 0 | 0 | not estimable | fewer than 20 observations |
| any side effect | treatment-specific | BPC-157 | dose only | 919 | 0 | fit | GEE with author-clustered robust 95% confidence intervals |
| distinct side-effect count | treatment-specific | BPC-157 | dose only | 919 | 0 | fit | GEE with author-clustered robust 95% confidence intervals |
| side-effect-level ordinal severity | treatment-specific | BPC-157 | dose only | 79 | 0 | fit | proportional-odds GEE with author-clustered robust 95% confidence intervals |
| maximum severity | treatment-specific | BPC-157 | dose only | 65 | 0 | fit | HC3 robust 95% confidence intervals |
| average severity | treatment-specific | BPC-157 | dose only | 65 | 0 | fit | HC3 robust 95% confidence intervals |
| any side effect | treatment-specific | Cerebrolysin | dose only | 3 | 0 | not estimable | fewer than 20 observations |
| distinct side-effect count | treatment-specific | Cerebrolysin | dose only | 3 | 0 | not estimable | fewer than 20 observations |
| side-effect-level ordinal severity | treatment-specific | Cerebrolysin | dose only | 0 | 0 | not estimable | fewer than 20 observations |
| maximum severity | treatment-specific | Cerebrolysin | dose only | 0 | 0 | not estimable | fewer than 20 observations |
| average severity | treatment-specific | Cerebrolysin | dose only | 0 | 0 | not estimable | fewer than 20 observations |
| any side effect | treatment-specific | Dihexa | dose only | 26 | 0 | fit | GEE with author-clustered robust 95% confidence intervals |
| distinct side-effect count | treatment-specific | Dihexa | dose only | 26 | 0 | fit | GEE with author-clustered robust 95% confidence intervals |
| side-effect-level ordinal severity | treatment-specific | Dihexa | dose only | 2 | 0 | not estimable | fewer than 20 observations |
| maximum severity | treatment-specific | Dihexa | dose only | 2 | 0 | not estimable | fewer than 20 observations |
| average severity | treatment-specific | Dihexa | dose only | 2 | 0 | not estimable | fewer than 20 observations |
| any side effect | treatment-specific | Lion's mane | dose only | 460 | 0 | fit | GEE with author-clustered robust 95% confidence intervals |
| distinct side-effect count | treatment-specific | Lion's mane | dose only | 460 | 0 | fit | GEE with author-clustered robust 95% confidence intervals |
| side-effect-level ordinal severity | treatment-specific | Lion's mane | dose only | 27 | 0 | fit | proportional-odds GEE with author-clustered robust 95% confidence intervals |
| maximum severity | treatment-specific | Lion's mane | dose only | 23 | 0 | fit | HC3 robust 95% confidence intervals |
| average severity | treatment-specific | Lion's mane | dose only | 23 | 0 | fit | HC3 robust 95% confidence intervals |
| any side effect | treatment-specific | NSI-189 | dose only | 64 | 0 | fit | GEE with author-clustered robust 95% confidence intervals |
| distinct side-effect count | treatment-specific | NSI-189 | dose only | 64 | 0 | fit | GEE with author-clustered robust 95% confidence intervals |
| side-effect-level ordinal severity | treatment-specific | NSI-189 | dose only | 13 | 0 | not estimable | fewer than 20 observations |
| maximum severity | treatment-specific | NSI-189 | dose only | 10 | 0 | not estimable | fewer than 20 observations |
| average severity | treatment-specific | NSI-189 | dose only | 10 | 0 | not estimable | fewer than 20 observations |
| any side effect | treatment-specific | Selank | dose only | 138 | 0 | fit | GEE with author-clustered robust 95% confidence intervals |
| distinct side-effect count | treatment-specific | Selank | dose only | 138 | 0 | fit | GEE with author-clustered robust 95% confidence intervals |
| side-effect-level ordinal severity | treatment-specific | Selank | dose only | 6 | 0 | not estimable | fewer than 20 observations |
| maximum severity | treatment-specific | Selank | dose only | 5 | 0 | not estimable | fewer than 20 observations |
| average severity | treatment-specific | Selank | dose only | 5 | 0 | not estimable | fewer than 20 observations |
| any side effect | treatment-specific | Semax | dose only | 195 | 0 | fit | GEE with author-clustered robust 95% confidence intervals |
| distinct side-effect count | treatment-specific | Semax | dose only | 195 | 0 | fit | GEE with author-clustered robust 95% confidence intervals |
| side-effect-level ordinal severity | treatment-specific | Semax | dose only | 12 | 0 | not estimable | fewer than 20 observations |
| maximum severity | treatment-specific | Semax | dose only | 10 | 0 | not estimable | fewer than 20 observations |
| average severity | treatment-specific | Semax | dose only | 10 | 0 | not estimable | fewer than 20 observations |
| any side effect | pooled with compound fixed effects | all compounds | dose only | 1876 | 0 | fit | GEE with author-clustered robust 95% confidence intervals |
| distinct side-effect count | pooled with compound fixed effects | all compounds | dose only | 1876 | 0 | fit | GEE with author-clustered robust 95% confidence intervals |
| side-effect-level ordinal severity | pooled with compound and safety-domain fixed effects | all compounds | dose only | 137 | 0 | fit | proportional-odds GEE with author-clustered robust 95% confidence intervals |
| maximum severity | pooled with compound fixed effects | all compounds | dose only | 118 | 0 | fit | author-clustered robust 95% confidence intervals |
| average severity | pooled with compound fixed effects | all compounds | dose only | 118 | 0 | fit | author-clustered robust 95% confidence intervals |
| any side effect | treatment-specific | 4'-DMA | route only | 17 | 0 | not estimable | fewer than 20 observations |
| distinct side-effect count | treatment-specific | 4'-DMA | route only | 17 | 0 | not estimable | fewer than 20 observations |
| side-effect-level ordinal severity | treatment-specific | 4'-DMA | route only | 0 | 2 | not estimable | fewer than 20 observations |
| maximum severity | treatment-specific | 4'-DMA | route only | 0 | 1 | not estimable | fewer than 20 observations |
| average severity | treatment-specific | 4'-DMA | route only | 0 | 1 | not estimable | fewer than 20 observations |
| any side effect | treatment-specific | 7,8-DHF | route only | 53 | 1 | not estimable | fewer than 2 supported route levels |
| distinct side-effect count | treatment-specific | 7,8-DHF | route only | 53 | 1 | not estimable | fewer than 2 supported route levels |
| side-effect-level ordinal severity | treatment-specific | 7,8-DHF | route only | 5 | 0 | not estimable | fewer than 20 observations |
| maximum severity | treatment-specific | 7,8-DHF | route only | 0 | 4 | not estimable | fewer than 20 observations |
| average severity | treatment-specific | 7,8-DHF | route only | 0 | 4 | not estimable | fewer than 20 observations |
| any side effect | treatment-specific | 9-MBC | route only | 7 | 0 | not estimable | fewer than 20 observations |
| distinct side-effect count | treatment-specific | 9-MBC | route only | 7 | 0 | not estimable | fewer than 20 observations |
| side-effect-level ordinal severity | treatment-specific | 9-MBC | route only | 0 | 2 | not estimable | fewer than 20 observations |
| maximum severity | treatment-specific | 9-MBC | route only | 0 | 1 | not estimable | fewer than 20 observations |
| average severity | treatment-specific | 9-MBC | route only | 0 | 1 | not estimable | fewer than 20 observations |
| any side effect | treatment-specific | BPC-157 | route only | 1169 | 0 | fit | GEE with author-clustered robust 95% confidence intervals |
| distinct side-effect count | treatment-specific | BPC-157 | route only | 1169 | 0 | fit | GEE with author-clustered robust 95% confidence intervals |
| side-effect-level ordinal severity | treatment-specific | BPC-157 | route only | 100 | 3 | fit | proportional-odds GEE with author-clustered robust 95% confidence intervals |
| maximum severity | treatment-specific | BPC-157 | route only | 84 | 3 | fit | HC3 robust 95% confidence intervals |
| average severity | treatment-specific | BPC-157 | route only | 84 | 3 | fit | HC3 robust 95% confidence intervals |
| any side effect | treatment-specific | Cerebrolysin | route only | 71 | 0 | fit | GEE with author-clustered robust 95% confidence intervals |
| distinct side-effect count | treatment-specific | Cerebrolysin | route only | 71 | 0 | fit | GEE with author-clustered robust 95% confidence intervals |
| side-effect-level ordinal severity | treatment-specific | Cerebrolysin | route only | 0 | 1 | not estimable | fewer than 20 observations |
| maximum severity | treatment-specific | Cerebrolysin | route only | 0 | 1 | not estimable | fewer than 20 observations |
| average severity | treatment-specific | Cerebrolysin | route only | 0 | 1 | not estimable | fewer than 20 observations |
| any side effect | treatment-specific | Dihexa | route only | 30 | 5 | fit | GEE with author-clustered robust 95% confidence intervals |
| distinct side-effect count | treatment-specific | Dihexa | route only | 30 | 5 | fit | GEE with author-clustered robust 95% confidence intervals |
| side-effect-level ordinal severity | treatment-specific | Dihexa | route only | 0 | 3 | not estimable | fewer than 20 observations |
| maximum severity | treatment-specific | Dihexa | route only | 0 | 3 | not estimable | fewer than 20 observations |
| average severity | treatment-specific | Dihexa | route only | 0 | 3 | not estimable | fewer than 20 observations |
| any side effect | treatment-specific | Lion's mane | route only | 24 | 0 | not estimable | fewer than 2 supported route levels |
| distinct side-effect count | treatment-specific | Lion's mane | route only | 24 | 0 | not estimable | fewer than 2 supported route levels |
| side-effect-level ordinal severity | treatment-specific | Lion's mane | route only | 0 | 0 | not estimable | fewer than 20 observations |
| maximum severity | treatment-specific | Lion's mane | route only | 0 | 0 | not estimable | fewer than 20 observations |
| average severity | treatment-specific | Lion's mane | route only | 0 | 0 | not estimable | fewer than 20 observations |
| any side effect | treatment-specific | NSI-189 | route only | 21 | 3 | not estimable | fewer than 2 supported route levels |
| distinct side-effect count | treatment-specific | NSI-189 | route only | 21 | 3 | not estimable | fewer than 2 supported route levels |
| side-effect-level ordinal severity | treatment-specific | NSI-189 | route only | 6 | 2 | not estimable | fewer than 20 observations |
| maximum severity | treatment-specific | NSI-189 | route only | 0 | 5 | not estimable | fewer than 20 observations |
| average severity | treatment-specific | NSI-189 | route only | 0 | 5 | not estimable | fewer than 20 observations |
| any side effect | treatment-specific | Selank | route only | 214 | 2 | fit | GEE with author-clustered robust 95% confidence intervals |
| distinct side-effect count | treatment-specific | Selank | route only | 214 | 2 | fit | GEE with author-clustered robust 95% confidence intervals |
| side-effect-level ordinal severity | treatment-specific | Selank | route only | 0 | 7 | not estimable | fewer than 20 observations |
| maximum severity | treatment-specific | Selank | route only | 0 | 6 | not estimable | fewer than 20 observations |
| average severity | treatment-specific | Selank | route only | 0 | 6 | not estimable | fewer than 20 observations |
| any side effect | treatment-specific | Semax | route only | 281 | 4 | fit | GEE with author-clustered robust 95% confidence intervals |
| distinct side-effect count | treatment-specific | Semax | route only | 281 | 4 | fit | GEE with author-clustered robust 95% confidence intervals |
| side-effect-level ordinal severity | treatment-specific | Semax | route only | 9 | 4 | not estimable | fewer than 20 observations |
| maximum severity | treatment-specific | Semax | route only | 7 | 3 | not estimable | fewer than 20 observations |
| average severity | treatment-specific | Semax | route only | 7 | 3 | not estimable | fewer than 20 observations |
| any side effect | pooled with compound fixed effects | all compounds | route only | 1902 | 0 | fit | GEE with author-clustered robust 95% confidence intervals |
| distinct side-effect count | pooled with compound fixed effects | all compounds | route only | 1902 | 0 | fit | GEE with author-clustered robust 95% confidence intervals |
| side-effect-level ordinal severity | pooled with compound and safety-domain fixed effects | all compounds | route only | 136 | 1 | fit | proportional-odds GEE with author-clustered robust 95% confidence intervals |
| maximum severity | pooled with compound fixed effects | all compounds | route only | 117 | 1 | fit | author-clustered robust 95% confidence intervals |
| average severity | pooled with compound fixed effects | all compounds | route only | 117 | 1 | fit | author-clustered robust 95% confidence intervals |
| any side effect | treatment-specific | 4'-DMA | dose + route | 7 | 0 | not estimable | fewer than 20 observations |
| distinct side-effect count | treatment-specific | 4'-DMA | dose + route | 7 | 0 | not estimable | fewer than 20 observations |
| side-effect-level ordinal severity | treatment-specific | 4'-DMA | dose + route | 0 | 2 | not estimable | fewer than 20 observations |
| maximum severity | treatment-specific | 4'-DMA | dose + route | 0 | 1 | not estimable | fewer than 20 observations |
| average severity | treatment-specific | 4'-DMA | dose + route | 0 | 1 | not estimable | fewer than 20 observations |
| any side effect | treatment-specific | 7,8-DHF | dose + route | 21 | 0 | not estimable | fewer than 2 supported route levels |
| distinct side-effect count | treatment-specific | 7,8-DHF | dose + route | 21 | 0 | not estimable | fewer than 2 supported route levels |
| side-effect-level ordinal severity | treatment-specific | 7,8-DHF | dose + route | 0 | 3 | not estimable | fewer than 20 observations |
| maximum severity | treatment-specific | 7,8-DHF | dose + route | 0 | 2 | not estimable | fewer than 20 observations |
| average severity | treatment-specific | 7,8-DHF | dose + route | 0 | 2 | not estimable | fewer than 20 observations |
| any side effect | treatment-specific | 9-MBC | dose + route | 0 | 1 | not estimable | fewer than 20 observations |
| distinct side-effect count | treatment-specific | 9-MBC | dose + route | 0 | 1 | not estimable | fewer than 20 observations |
| side-effect-level ordinal severity | treatment-specific | 9-MBC | dose + route | 0 | 0 | not estimable | fewer than 20 observations |
| maximum severity | treatment-specific | 9-MBC | dose + route | 0 | 0 | not estimable | fewer than 20 observations |
| average severity | treatment-specific | 9-MBC | dose + route | 0 | 0 | not estimable | fewer than 20 observations |
| any side effect | treatment-specific | BPC-157 | dose + route | 417 | 1 | fit | GEE with author-clustered robust 95% confidence intervals |
| distinct side-effect count | treatment-specific | BPC-157 | dose + route | 417 | 1 | fit | GEE with author-clustered robust 95% confidence intervals |
| side-effect-level ordinal severity | treatment-specific | BPC-157 | dose + route | 37 | 2 | fit | proportional-odds GEE with author-clustered robust 95% confidence intervals |
| maximum severity | treatment-specific | BPC-157 | dose + route | 33 | 2 | fit | HC3 robust 95% confidence intervals |
| average severity | treatment-specific | BPC-157 | dose + route | 33 | 2 | fit | HC3 robust 95% confidence intervals |
| any side effect | treatment-specific | Cerebrolysin | dose + route | 0 | 2 | not estimable | fewer than 20 observations |
| distinct side-effect count | treatment-specific | Cerebrolysin | dose + route | 0 | 2 | not estimable | fewer than 20 observations |
| side-effect-level ordinal severity | treatment-specific | Cerebrolysin | dose + route | 0 | 0 | not estimable | fewer than 20 observations |
| maximum severity | treatment-specific | Cerebrolysin | dose + route | 0 | 0 | not estimable | fewer than 20 observations |
| average severity | treatment-specific | Cerebrolysin | dose + route | 0 | 0 | not estimable | fewer than 20 observations |
| any side effect | treatment-specific | Dihexa | dose + route | 11 | 3 | not estimable | fewer than 20 observations |
| distinct side-effect count | treatment-specific | Dihexa | dose + route | 11 | 3 | not estimable | fewer than 20 observations |
| side-effect-level ordinal severity | treatment-specific | Dihexa | dose + route | 0 | 1 | not estimable | fewer than 20 observations |
| maximum severity | treatment-specific | Dihexa | dose + route | 0 | 1 | not estimable | fewer than 20 observations |
| average severity | treatment-specific | Dihexa | dose + route | 0 | 1 | not estimable | fewer than 20 observations |
| any side effect | treatment-specific | Lion's mane | dose + route | 6 | 0 | not estimable | fewer than 20 observations |
| distinct side-effect count | treatment-specific | Lion's mane | dose + route | 6 | 0 | not estimable | fewer than 20 observations |
| side-effect-level ordinal severity | treatment-specific | Lion's mane | dose + route | 0 | 0 | not estimable | fewer than 20 observations |
| maximum severity | treatment-specific | Lion's mane | dose + route | 0 | 0 | not estimable | fewer than 20 observations |
| average severity | treatment-specific | Lion's mane | dose + route | 0 | 0 | not estimable | fewer than 20 observations |
| any side effect | treatment-specific | NSI-189 | dose + route | 15 | 1 | not estimable | fewer than 20 observations |
| distinct side-effect count | treatment-specific | NSI-189 | dose + route | 15 | 1 | not estimable | fewer than 20 observations |
| side-effect-level ordinal severity | treatment-specific | NSI-189 | dose + route | 0 | 4 | not estimable | fewer than 20 observations |
| maximum severity | treatment-specific | NSI-189 | dose + route | 0 | 2 | not estimable | fewer than 20 observations |
| average severity | treatment-specific | NSI-189 | dose + route | 0 | 2 | not estimable | fewer than 20 observations |
| any side effect | treatment-specific | Selank | dose + route | 54 | 0 | fit | GEE with author-clustered robust 95% confidence intervals |
| distinct side-effect count | treatment-specific | Selank | dose + route | 54 | 0 | fit | GEE with author-clustered robust 95% confidence intervals |
| side-effect-level ordinal severity | treatment-specific | Selank | dose + route | 0 | 4 | not estimable | fewer than 20 observations |
| maximum severity | treatment-specific | Selank | dose + route | 0 | 3 | not estimable | fewer than 20 observations |
| average severity | treatment-specific | Selank | dose + route | 0 | 3 | not estimable | fewer than 20 observations |
| any side effect | treatment-specific | Semax | dose + route | 70 | 1 | fit | GEE with author-clustered robust 95% confidence intervals |
| distinct side-effect count | treatment-specific | Semax | dose + route | 70 | 1 | fit | GEE with author-clustered robust 95% confidence intervals |
| side-effect-level ordinal severity | treatment-specific | Semax | dose + route | 5 | 0 | not estimable | fewer than 20 observations |
| maximum severity | treatment-specific | Semax | dose + route | 0 | 4 | not estimable | fewer than 20 observations |
| average severity | treatment-specific | Semax | dose + route | 0 | 4 | not estimable | fewer than 20 observations |
| any side effect | pooled with compound fixed effects | all compounds | dose + route | 607 | 3 | fit | GEE with author-clustered robust 95% confidence intervals |
| distinct side-effect count | pooled with compound fixed effects | all compounds | dose + route | 607 | 3 | fit | GEE with author-clustered robust 95% confidence intervals |
| side-effect-level ordinal severity | pooled with compound and safety-domain fixed effects | all compounds | dose + route | 37 | 9 | not estimable | fewer than 2 treatments with adequate graded-effect support |
| maximum severity | pooled with compound fixed effects | all compounds | dose + route | 40 | 8 | fit | author-clustered robust 95% confidence intervals |
| average severity | pooled with compound fixed effects | all compounds | dose + route | 40 | 8 | fit | author-clustered robust 95% confidence intervals |
| any side effect | treatment-specific | 4'-DMA | dose + route + interaction | 7 | 0 | not estimable | fewer than 20 observations |
| distinct side-effect count | treatment-specific | 4'-DMA | dose + route + interaction | 7 | 0 | not estimable | fewer than 20 observations |
| side-effect-level ordinal severity | treatment-specific | 4'-DMA | dose + route + interaction | 0 | 2 | not estimable | fewer than 20 observations |
| maximum severity | treatment-specific | 4'-DMA | dose + route + interaction | 0 | 1 | not estimable | fewer than 20 observations |
| average severity | treatment-specific | 4'-DMA | dose + route + interaction | 0 | 1 | not estimable | fewer than 20 observations |
| any side effect | treatment-specific | 7,8-DHF | dose + route + interaction | 21 | 0 | not estimable | fewer than 2 supported route levels |
| distinct side-effect count | treatment-specific | 7,8-DHF | dose + route + interaction | 21 | 0 | not estimable | fewer than 2 supported route levels |
| side-effect-level ordinal severity | treatment-specific | 7,8-DHF | dose + route + interaction | 0 | 3 | not estimable | fewer than 20 observations |
| maximum severity | treatment-specific | 7,8-DHF | dose + route + interaction | 0 | 2 | not estimable | fewer than 20 observations |
| average severity | treatment-specific | 7,8-DHF | dose + route + interaction | 0 | 2 | not estimable | fewer than 20 observations |
| any side effect | treatment-specific | 9-MBC | dose + route + interaction | 0 | 1 | not estimable | fewer than 20 observations |
| distinct side-effect count | treatment-specific | 9-MBC | dose + route + interaction | 0 | 1 | not estimable | fewer than 20 observations |
| side-effect-level ordinal severity | treatment-specific | 9-MBC | dose + route + interaction | 0 | 0 | not estimable | fewer than 20 observations |
| maximum severity | treatment-specific | 9-MBC | dose + route + interaction | 0 | 0 | not estimable | fewer than 20 observations |
| average severity | treatment-specific | 9-MBC | dose + route + interaction | 0 | 0 | not estimable | fewer than 20 observations |
| any side effect | treatment-specific | BPC-157 | dose + route + interaction | 417 | 1 | fit | GEE with author-clustered robust 95% confidence intervals |
| distinct side-effect count | treatment-specific | BPC-157 | dose + route + interaction | 417 | 1 | fit | GEE with author-clustered robust 95% confidence intervals |
| side-effect-level ordinal severity | treatment-specific | BPC-157 | dose + route + interaction | 37 | 2 | fit | proportional-odds GEE with author-clustered robust 95% confidence intervals |
| maximum severity | treatment-specific | BPC-157 | dose + route + interaction | 33 | 2 | fit | HC3 robust 95% confidence intervals |
| average severity | treatment-specific | BPC-157 | dose + route + interaction | 33 | 2 | fit | HC3 robust 95% confidence intervals |
| any side effect | treatment-specific | Cerebrolysin | dose + route + interaction | 0 | 2 | not estimable | fewer than 20 observations |
| distinct side-effect count | treatment-specific | Cerebrolysin | dose + route + interaction | 0 | 2 | not estimable | fewer than 20 observations |
| side-effect-level ordinal severity | treatment-specific | Cerebrolysin | dose + route + interaction | 0 | 0 | not estimable | fewer than 20 observations |
| maximum severity | treatment-specific | Cerebrolysin | dose + route + interaction | 0 | 0 | not estimable | fewer than 20 observations |
| average severity | treatment-specific | Cerebrolysin | dose + route + interaction | 0 | 0 | not estimable | fewer than 20 observations |
| any side effect | treatment-specific | Dihexa | dose + route + interaction | 11 | 3 | not estimable | fewer than 20 observations |
| distinct side-effect count | treatment-specific | Dihexa | dose + route + interaction | 11 | 3 | not estimable | fewer than 20 observations |
| side-effect-level ordinal severity | treatment-specific | Dihexa | dose + route + interaction | 0 | 1 | not estimable | fewer than 20 observations |
| maximum severity | treatment-specific | Dihexa | dose + route + interaction | 0 | 1 | not estimable | fewer than 20 observations |
| average severity | treatment-specific | Dihexa | dose + route + interaction | 0 | 1 | not estimable | fewer than 20 observations |
| any side effect | treatment-specific | Lion's mane | dose + route + interaction | 6 | 0 | not estimable | fewer than 20 observations |
| distinct side-effect count | treatment-specific | Lion's mane | dose + route + interaction | 6 | 0 | not estimable | fewer than 20 observations |
| side-effect-level ordinal severity | treatment-specific | Lion's mane | dose + route + interaction | 0 | 0 | not estimable | fewer than 20 observations |
| maximum severity | treatment-specific | Lion's mane | dose + route + interaction | 0 | 0 | not estimable | fewer than 20 observations |
| average severity | treatment-specific | Lion's mane | dose + route + interaction | 0 | 0 | not estimable | fewer than 20 observations |
| any side effect | treatment-specific | NSI-189 | dose + route + interaction | 15 | 1 | not estimable | fewer than 20 observations |
| distinct side-effect count | treatment-specific | NSI-189 | dose + route + interaction | 15 | 1 | not estimable | fewer than 20 observations |
| side-effect-level ordinal severity | treatment-specific | NSI-189 | dose + route + interaction | 0 | 4 | not estimable | fewer than 20 observations |
| maximum severity | treatment-specific | NSI-189 | dose + route + interaction | 0 | 2 | not estimable | fewer than 20 observations |
| average severity | treatment-specific | NSI-189 | dose + route + interaction | 0 | 2 | not estimable | fewer than 20 observations |
| any side effect | treatment-specific | Selank | dose + route + interaction | 54 | 0 | fit | GEE with author-clustered robust 95% confidence intervals |
| distinct side-effect count | treatment-specific | Selank | dose + route + interaction | 54 | 0 | fit | GEE with author-clustered robust 95% confidence intervals |
| side-effect-level ordinal severity | treatment-specific | Selank | dose + route + interaction | 0 | 4 | not estimable | fewer than 20 observations |
| maximum severity | treatment-specific | Selank | dose + route + interaction | 0 | 3 | not estimable | fewer than 20 observations |
| average severity | treatment-specific | Selank | dose + route + interaction | 0 | 3 | not estimable | fewer than 20 observations |
| any side effect | treatment-specific | Semax | dose + route + interaction | 70 | 1 | fit | GEE with author-clustered robust 95% confidence intervals |
| distinct side-effect count | treatment-specific | Semax | dose + route + interaction | 70 | 1 | fit | GEE with author-clustered robust 95% confidence intervals |
| side-effect-level ordinal severity | treatment-specific | Semax | dose + route + interaction | 5 | 0 | not estimable | fewer than 20 observations |
| maximum severity | treatment-specific | Semax | dose + route + interaction | 0 | 4 | not estimable | fewer than 20 observations |
| average severity | treatment-specific | Semax | dose + route + interaction | 0 | 4 | not estimable | fewer than 20 observations |
| any side effect | pooled with compound fixed effects | all compounds | dose + route + interaction | 607 | 3 | fit | GEE with author-clustered robust 95% confidence intervals |
| distinct side-effect count | pooled with compound fixed effects | all compounds | dose + route + interaction | 607 | 3 | fit | GEE with author-clustered robust 95% confidence intervals |
| side-effect-level ordinal severity | pooled with compound and safety-domain fixed effects | all compounds | dose + route + interaction | 37 | 9 | not estimable | fewer than 2 treatments with adequate graded-effect support |
| maximum severity | pooled with compound fixed effects | all compounds | dose + route + interaction | 40 | 8 | fit | author-clustered robust 95% confidence intervals |
| average severity | pooled with compound fixed effects | all compounds | dose + route + interaction | 40 | 8 | fit | author-clustered robust 95% confidence intervals |

## Maximum-severity model statuses

| Analysis set | Scope | Compound | Model | Linked authors | Eligible authors | Rare-route exclusions | Status | Reason |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| primary | treatment-specific | 4'-DMA | dose only | 1 | 1 | 0 | not estimable | fewer than 20 eligible authors |
| primary | treatment-specific | 7,8-DHF | dose only | 2 | 2 | 0 | not estimable | fewer than 20 eligible authors |
| primary | treatment-specific | 9-MBC | dose only | 0 | 0 | 0 | not estimable | fewer than 20 eligible authors |
| primary | treatment-specific | BPC-157 | dose only | 65 | 65 | 0 | fit | HC3 heteroskedasticity-robust 95% CI |
| primary | treatment-specific | Cerebrolysin | dose only | 0 | 0 | 0 | not estimable | fewer than 20 eligible authors |
| primary | treatment-specific | Dihexa | dose only | 2 | 2 | 0 | not estimable | fewer than 20 eligible authors |
| primary | treatment-specific | Lion's mane | dose only | 23 | 23 | 0 | fit | HC3 heteroskedasticity-robust 95% CI |
| primary | treatment-specific | NSI-189 | dose only | 10 | 10 | 0 | not estimable | fewer than 20 eligible authors |
| primary | treatment-specific | Selank | dose only | 5 | 5 | 0 | not estimable | fewer than 20 eligible authors |
| primary | treatment-specific | Semax | dose only | 10 | 10 | 0 | not estimable | fewer than 20 eligible authors |
| primary | pooled with compound fixed effects | all compounds | dose only | 118 | 118 | 0 | fit | cluster-robust 95% CI by author |
| primary | treatment-specific | 4'-DMA | route only | 1 | 0 | 1 | not estimable | fewer than 20 eligible authors after 1 exclusions from route levels with fewer than 5 within-treatment observations |
| primary | treatment-specific | 7,8-DHF | route only | 4 | 0 | 4 | not estimable | fewer than 20 eligible authors after 4 exclusions from route levels with fewer than 5 within-treatment observations |
| primary | treatment-specific | 9-MBC | route only | 1 | 0 | 1 | not estimable | fewer than 20 eligible authors after 1 exclusions from route levels with fewer than 5 within-treatment observations |
| primary | treatment-specific | BPC-157 | route only | 87 | 84 | 3 | fit | HC3 heteroskedasticity-robust 95% CI |
| primary | treatment-specific | Cerebrolysin | route only | 1 | 0 | 1 | not estimable | fewer than 20 eligible authors after 1 exclusions from route levels with fewer than 5 within-treatment observations |
| primary | treatment-specific | Dihexa | route only | 3 | 0 | 3 | not estimable | fewer than 20 eligible authors after 3 exclusions from route levels with fewer than 5 within-treatment observations |
| primary | treatment-specific | Lion's mane | route only | 0 | 0 | 0 | not estimable | fewer than 20 eligible authors |
| primary | treatment-specific | NSI-189 | route only | 5 | 0 | 5 | not estimable | fewer than 20 eligible authors after 5 exclusions from route levels with fewer than 5 within-treatment observations |
| primary | treatment-specific | Selank | route only | 6 | 0 | 6 | not estimable | fewer than 20 eligible authors after 6 exclusions from route levels with fewer than 5 within-treatment observations |
| primary | treatment-specific | Semax | route only | 10 | 7 | 3 | not estimable | fewer than 20 eligible authors after 3 exclusions from route levels with fewer than 5 within-treatment observations |
| primary | pooled with compound fixed effects | all compounds | route only | 118 | 117 | 1 | fit | cluster-robust 95% CI by author |
| primary | treatment-specific | 4'-DMA | dose + route | 1 | 0 | 1 | not estimable | fewer than 20 eligible authors after 1 exclusions from route levels with fewer than 5 within-treatment observations |
| primary | treatment-specific | 7,8-DHF | dose + route | 2 | 0 | 2 | not estimable | fewer than 20 eligible authors after 2 exclusions from route levels with fewer than 5 within-treatment observations |
| primary | treatment-specific | 9-MBC | dose + route | 0 | 0 | 0 | not estimable | fewer than 20 eligible authors |
| primary | treatment-specific | BPC-157 | dose + route | 35 | 33 | 2 | fit | HC3 heteroskedasticity-robust 95% CI |
| primary | treatment-specific | Cerebrolysin | dose + route | 0 | 0 | 0 | not estimable | fewer than 20 eligible authors |
| primary | treatment-specific | Dihexa | dose + route | 1 | 0 | 1 | not estimable | fewer than 20 eligible authors after 1 exclusions from route levels with fewer than 5 within-treatment observations |
| primary | treatment-specific | Lion's mane | dose + route | 0 | 0 | 0 | not estimable | fewer than 20 eligible authors |
| primary | treatment-specific | NSI-189 | dose + route | 2 | 0 | 2 | not estimable | fewer than 20 eligible authors after 2 exclusions from route levels with fewer than 5 within-treatment observations |
| primary | treatment-specific | Selank | dose + route | 3 | 0 | 3 | not estimable | fewer than 20 eligible authors after 3 exclusions from route levels with fewer than 5 within-treatment observations |
| primary | treatment-specific | Semax | dose + route | 4 | 0 | 4 | not estimable | fewer than 20 eligible authors after 4 exclusions from route levels with fewer than 5 within-treatment observations |
| primary | pooled with compound fixed effects | all compounds | dose + route | 48 | 40 | 8 | fit | cluster-robust 95% CI by author |
| all linked doses | treatment-specific | 4'-DMA | dose only | 1 | 1 | 0 | not estimable | fewer than 20 eligible authors |
| all linked doses | treatment-specific | 7,8-DHF | dose only | 2 | 2 | 0 | not estimable | fewer than 20 eligible authors |
| all linked doses | treatment-specific | 9-MBC | dose only | 0 | 0 | 0 | not estimable | fewer than 20 eligible authors |
| all linked doses | treatment-specific | BPC-157 | dose only | 76 | 76 | 0 | fit | HC3 heteroskedasticity-robust 95% CI |
| all linked doses | treatment-specific | Cerebrolysin | dose only | 0 | 0 | 0 | not estimable | fewer than 20 eligible authors |
| all linked doses | treatment-specific | Dihexa | dose only | 2 | 2 | 0 | not estimable | fewer than 20 eligible authors |
| all linked doses | treatment-specific | Lion's mane | dose only | 23 | 23 | 0 | fit | HC3 heteroskedasticity-robust 95% CI |
| all linked doses | treatment-specific | NSI-189 | dose only | 10 | 10 | 0 | not estimable | fewer than 20 eligible authors |
| all linked doses | treatment-specific | Selank | dose only | 5 | 5 | 0 | not estimable | fewer than 20 eligible authors |
| all linked doses | treatment-specific | Semax | dose only | 10 | 10 | 0 | not estimable | fewer than 20 eligible authors |
| all linked doses | pooled with compound fixed effects | all compounds | dose only | 129 | 129 | 0 | fit | cluster-robust 95% CI by author |
| all linked doses | treatment-specific | 4'-DMA | route only | 1 | 0 | 1 | not estimable | fewer than 20 eligible authors after 1 exclusions from route levels with fewer than 5 within-treatment observations |
| all linked doses | treatment-specific | 7,8-DHF | route only | 4 | 0 | 4 | not estimable | fewer than 20 eligible authors after 4 exclusions from route levels with fewer than 5 within-treatment observations |
| all linked doses | treatment-specific | 9-MBC | route only | 1 | 0 | 1 | not estimable | fewer than 20 eligible authors after 1 exclusions from route levels with fewer than 5 within-treatment observations |
| all linked doses | treatment-specific | BPC-157 | route only | 87 | 84 | 3 | fit | HC3 heteroskedasticity-robust 95% CI |
| all linked doses | treatment-specific | Cerebrolysin | route only | 1 | 0 | 1 | not estimable | fewer than 20 eligible authors after 1 exclusions from route levels with fewer than 5 within-treatment observations |
| all linked doses | treatment-specific | Dihexa | route only | 3 | 0 | 3 | not estimable | fewer than 20 eligible authors after 3 exclusions from route levels with fewer than 5 within-treatment observations |
| all linked doses | treatment-specific | Lion's mane | route only | 0 | 0 | 0 | not estimable | fewer than 20 eligible authors |
| all linked doses | treatment-specific | NSI-189 | route only | 5 | 0 | 5 | not estimable | fewer than 20 eligible authors after 5 exclusions from route levels with fewer than 5 within-treatment observations |
| all linked doses | treatment-specific | Selank | route only | 6 | 0 | 6 | not estimable | fewer than 20 eligible authors after 6 exclusions from route levels with fewer than 5 within-treatment observations |
| all linked doses | treatment-specific | Semax | route only | 10 | 7 | 3 | not estimable | fewer than 20 eligible authors after 3 exclusions from route levels with fewer than 5 within-treatment observations |
| all linked doses | pooled with compound fixed effects | all compounds | route only | 118 | 117 | 1 | fit | cluster-robust 95% CI by author |
| all linked doses | treatment-specific | 4'-DMA | dose + route | 1 | 0 | 1 | not estimable | fewer than 20 eligible authors after 1 exclusions from route levels with fewer than 5 within-treatment observations |
| all linked doses | treatment-specific | 7,8-DHF | dose + route | 2 | 0 | 2 | not estimable | fewer than 20 eligible authors after 2 exclusions from route levels with fewer than 5 within-treatment observations |
| all linked doses | treatment-specific | 9-MBC | dose + route | 0 | 0 | 0 | not estimable | fewer than 20 eligible authors |
| all linked doses | treatment-specific | BPC-157 | dose + route | 39 | 37 | 2 | fit | HC3 heteroskedasticity-robust 95% CI |
| all linked doses | treatment-specific | Cerebrolysin | dose + route | 0 | 0 | 0 | not estimable | fewer than 20 eligible authors |
| all linked doses | treatment-specific | Dihexa | dose + route | 1 | 0 | 1 | not estimable | fewer than 20 eligible authors after 1 exclusions from route levels with fewer than 5 within-treatment observations |
| all linked doses | treatment-specific | Lion's mane | dose + route | 0 | 0 | 0 | not estimable | fewer than 20 eligible authors |
| all linked doses | treatment-specific | NSI-189 | dose + route | 2 | 0 | 2 | not estimable | fewer than 20 eligible authors after 2 exclusions from route levels with fewer than 5 within-treatment observations |
| all linked doses | treatment-specific | Selank | dose + route | 3 | 0 | 3 | not estimable | fewer than 20 eligible authors after 3 exclusions from route levels with fewer than 5 within-treatment observations |
| all linked doses | treatment-specific | Semax | dose + route | 4 | 0 | 4 | not estimable | fewer than 20 eligible authors after 4 exclusions from route levels with fewer than 5 within-treatment observations |
| all linked doses | pooled with compound fixed effects | all compounds | dose + route | 52 | 44 | 8 | fit | cluster-robust 95% CI by author |
