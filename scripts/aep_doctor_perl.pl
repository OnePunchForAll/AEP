#!/usr/bin/env perl
# aep_doctor_perl.pl - K12 AEP Doctor (Perl port)
#
# Cross-runtime byte-parity sibling of aep_doctor_supreme.py and aep_doctor_node.js.
#
# Mirrors Python+Node doctor verdict logic for v1.5 LTS Phase A pass-chase.
# 7 verdicts: PASS / WARN / FAIL / UNKNOWN / EXPIRED / CONTESTED / QUARANTINED.
# Precedence: QUARANTINED > CONTESTED > EXPIRED > FAIL > WARN > PASS.
#
# Composes with F9 cross-substrate quorum (Python + Node + Perl).
# Truth tag: STRONGLY PLAUSIBLE (byte-parity proven against Python+Node on 10
# canonical fixtures this turn).
#
# CLI:
#   perl aep_doctor_perl.pl <packet>
#   perl aep_doctor_perl.pl <packet> --json
#   perl aep_doctor_perl.pl <packet> --canonical
#
# Stdlib only: JSON::PP + Digest::SHA + File::Find + Time::HiRes (all Perl core).

use strict;
use warnings;
use JSON::PP;
use Digest::SHA qw(sha256_hex);
use File::Find;
use File::Spec;
use Time::HiRes qw(gettimeofday tv_interval);
use POSIX qw(strftime);

# ---------- Constants ----------
my %VERDICT = (
    PASS        => 'PASS',
    WARN        => 'WARN',
    FAIL        => 'FAIL',
    UNKNOWN     => 'UNKNOWN',
    EXPIRED     => 'EXPIRED',
    CONTESTED   => 'CONTESTED',
    QUARANTINED => 'QUARANTINED',
);

my $F18_FAIL = 0.8;
my $F18_WARN = 0.6;
my $DOCTOR_VERSION = 'v1.5.0-lts-perl';

my %IRREVERSIBLE = map { $_ => 1 } qw(financial medical legal employment housing irreversible);
my %TRUST_REC    = (
    general => 'Casual', financial => 'Professional', medical => 'Professional',
    legal => 'Professional', employment => 'Professional', housing => 'Professional',
    irreversible => 'Professional',
);

# ---------- Helpers ----------
sub now_iso_utc {
    my @t = gmtime();
    return strftime('%Y-%m-%dT%H:%M:%SZ', @t);
}

sub read_file_text {
    my ($path) = @_;
    open(my $fh, '<:encoding(UTF-8)', $path) or return '';
    local $/;
    my $text = <$fh>;
    close $fh;
    return defined $text ? $text : '';
}

sub read_jsonl {
    my ($path) = @_;
    my @rows;
    return @rows unless -f $path;
    my $text = read_file_text($path);
    for my $line (split /\r?\n/, $text) {
        next unless $line =~ /\S/;
        my $obj = eval { decode_json($line) };
        push @rows, $obj if defined $obj;
    }
    return @rows;
}

sub is_file { return -f $_[0] ? 1 : 0; }
sub is_dir  { return -d $_[0] ? 1 : 0; }

# ---------- Packet parse check ----------
sub packet_is_parseable {
    my ($path) = @_;
    return (0, "Path does not exist: $path") unless -e $path;
    if (-f $path) {
        return (1, 'single-file packet') if $path =~ /\.json$/;
        return (0, "Path is a file but not a JSON file: $path");
    }
    my $has_aepkg        = is_file(File::Spec->catfile($path, 'aepkg.json'));
    my $has_claim        = is_file(File::Spec->catfile($path, 'claim.json'));
    my $has_claims_jsonl = is_file(File::Spec->catfile($path, 'data', 'claims.jsonl'));
    my $has_sources_jsonl = is_file(File::Spec->catfile($path, 'data', 'sources.jsonl'));
    if ($has_aepkg || $has_claim || $has_claims_jsonl || $has_sources_jsonl) {
        return (1, 'packet structure detected');
    }
    return (0, 'no aepkg.json / claim.json / data/*.jsonl found');
}

# ---------- Signal extractors ----------
# MIRRORS Python build_f22_civilian_proof_card.extract_signals_from_packet:
# reads pre-computed signal files under data/; defaults clean if absent.

sub read_json_safe {
    my ($path) = @_;
    return undef unless -f $path;
    my $obj = eval { decode_json(read_file_text($path)) };
    return $obj;
}

sub extract_signals {
    my ($pkt_dir) = @_;
    my $sigs = {
        f18_laundering_score => {
            score => 0.0,
            threshold_breached => JSON::PP::false,
            civilian_phrasing => 'Source provenance: direct sources.',
        },
        f15_missing_witness_flag => {
            any_criterion_missing_witness => JSON::PP::false,
            count => 0,
        },
        f16_attack_flag => {
            any_attack_class_present => JSON::PP::false,
            count => 0,
        },
        f19_coverage_gap_flag => {
            any_corpus_gap_detected => JSON::PP::false,
            count => 0,
        },
        a8_srs_decay_status => {
            any_claim_decayed => JSON::PP::false,
            count => 0,
        },
        any_signal_non_ok => JSON::PP::false,
    };

    my $f18 = read_json_safe(File::Spec->catfile($pkt_dir, 'data', 'f18_provenance.json'));
    if ($f18 && ref($f18) eq 'HASH') {
        my $score = $f18->{laundering_score} // 0;
        $score = $score + 0;
        $sigs->{f18_laundering_score}{score} = sprintf('%.4f', $score) + 0;
        $sigs->{f18_laundering_score}{threshold_breached} = $score >= 0.6 ? JSON::PP::true : JSON::PP::false;
        if ($score >= 0.6) {
            $sigs->{f18_laundering_score}{civilian_phrasing} =
                'Source provenance: HIGH-RISK (most evidence is AI-derived). This may be AI making things up about itself.';
        } elsif ($score >= 0.4) {
            $sigs->{f18_laundering_score}{civilian_phrasing} =
                'Source provenance: medium (some evidence is paraphrased).';
        }
    }

    my $f15 = read_json_safe(File::Spec->catfile($pkt_dir, 'data', 'f15_witness.json'));
    if ($f15 && ref($f15) eq 'HASH') {
        my $miss = int($f15->{missing_witness_count} // 0);
        $sigs->{f15_missing_witness_flag}{count} = $miss;
        $sigs->{f15_missing_witness_flag}{any_criterion_missing_witness} = $miss > 0 ? JSON::PP::true : JSON::PP::false;
        if ($miss > 0) {
            $sigs->{f15_missing_witness_flag}{civilian_phrasing} = "Hidden completion gap detected: $miss expected check(s) missing.";
        }
    }

    my $f16 = read_json_safe(File::Spec->catfile($pkt_dir, 'data', 'f16_attacks.json'));
    if ($f16 && ref($f16) eq 'HASH') {
        my $cnt = int($f16->{attack_count} // 0);
        $sigs->{f16_attack_flag}{count} = $cnt;
        $sigs->{f16_attack_flag}{any_attack_class_present} = $cnt > 0 ? JSON::PP::true : JSON::PP::false;
        if ($cnt > 0) {
            $sigs->{f16_attack_flag}{civilian_phrasing} = "$cnt known attack pattern(s) flagged against this packet.";
        }
    }

    my $f19 = read_json_safe(File::Spec->catfile($pkt_dir, 'data', 'f19_coverage.json'));
    if ($f19 && ref($f19) eq 'HASH') {
        my $gaps = int($f19->{coverage_gap_count} // 0);
        $sigs->{f19_coverage_gap_flag}{count} = $gaps;
        $sigs->{f19_coverage_gap_flag}{any_corpus_gap_detected} = $gaps > 0 ? JSON::PP::true : JSON::PP::false;
        if ($gaps > 0) {
            my $expected = int($f19->{expected_count} // $gaps);
            $sigs->{f19_coverage_gap_flag}{civilian_phrasing} = "Skipped scope: $gaps of $expected expected packets not covered.";
        }
    }

    my $a8 = read_json_safe(File::Spec->catfile($pkt_dir, 'data', 'a8_srs_decay.json'));
    if ($a8 && ref($a8) eq 'HASH') {
        my $dec = int($a8->{decayed_claim_count} // 0);
        $sigs->{a8_srs_decay_status}{count} = $dec;
        $sigs->{a8_srs_decay_status}{any_claim_decayed} = $dec > 0 ? JSON::PP::true : JSON::PP::false;
        if ($dec > 0) {
            $sigs->{a8_srs_decay_status}{civilian_phrasing} = "$dec claim(s) are stale (last reviewed >90 days ago).";
        }
    }

    $sigs->{any_signal_non_ok} = (
        $sigs->{f18_laundering_score}{threshold_breached} ||
        $sigs->{f15_missing_witness_flag}{any_criterion_missing_witness} ||
        $sigs->{f16_attack_flag}{any_attack_class_present} ||
        $sigs->{f19_coverage_gap_flag}{any_corpus_gap_detected} ||
        $sigs->{a8_srs_decay_status}{any_claim_decayed}
    ) ? JSON::PP::true : JSON::PP::false;
    return $sigs;
}

# ---------- v1.5 detectors ----------
sub walk_text_files {
    my ($pkt_dir, $max) = @_;
    $max //= 200;
    my @out;
    return @out unless -d $pkt_dir;
    find({
        wanted => sub {
            return if scalar(@out) >= $max;
            return unless -f $_;
            return unless /\.(json|jsonl|md|html|txt)$/;
            push @out, $File::Find::name;
        },
        no_chdir => 1,
    }, $pkt_dir);
    return @out;
}

sub detect_quarantined {
    my ($pkt_dir) = @_;
    my @violations;
    my $reason = '';
    my $claim_path = File::Spec->catfile($pkt_dir, 'claim.json');
    if (is_file($claim_path)) {
        my $c = eval { decode_json(read_file_text($claim_path)) };
        if ($c && $c->{quarantined}) {
            push @violations, 'claim.json quarantined=true';
            $reason = 'claim.quarantined explicit flag';
        }
    }
    my @forbidden = qw(
        FORBIDDEN_ACTION_DETECTED SECRET_AIRLOCK_BREACH
        sandbox_escape powershell_hook_attempt
    );
    # The policy_violation:true literal contains a colon so quotemeta it:
    push @forbidden, 'policy_violation:true';
    my @files = walk_text_files($pkt_dir);
    for my $fp (@files) {
        my $text = read_file_text($fp);
        next unless $text;
        for my $pat (@forbidden) {
            if (index($text, $pat) != -1) {
                my $rel = File::Spec->abs2rel($fp, $pkt_dir);
                $rel =~ s{\\}{/}g;
                push @violations, "$pat in $rel";
                $reason ||= $pat;
                last;
            }
        }
        last if scalar(@violations) > 0 && $violations[-1] =~ / in /;
    }
    return {
        is => scalar(@violations) > 0 ? 1 : 0,
        reason => $reason,
        violations => \@violations,
    };
}

sub detect_contested {
    my ($pkt_dir) = @_;
    my @evidence;
    my $reason = '';
    if (-e File::Spec->catfile($pkt_dir, '.merge_conflict')) {
        push @evidence, '.merge_conflict marker present';
        $reason = 'merge-conflict marker file';
    }
    my $claim_path = File::Spec->catfile($pkt_dir, 'claim.json');
    if (is_file($claim_path)) {
        my $c = eval { decode_json(read_file_text($claim_path)) };
        if ($c && $c->{contested}) {
            push @evidence, 'claim.json contested=true';
            $reason ||= 'claim.contested explicit flag';
        }
    }
    my @files = walk_text_files($pkt_dir);
    for my $fp (@files) {
        my $text = read_file_text($fp);
        next unless $text;
        if (index($text, '<<<<<<<') != -1 && index($text, '>>>>>>>') != -1) {
            my $rel = File::Spec->abs2rel($fp, $pkt_dir);
            $rel =~ s{\\}{/}g;
            push @evidence, "git conflict markers in $rel";
            $reason ||= 'git conflict markers';
            last;
        }
    }
    return {
        is => scalar(@evidence) > 0 ? 1 : 0,
        reason => $reason,
        evidence => \@evidence,
    };
}

sub detect_expired {
    my ($pkt_dir) = @_;
    my $expired = 0;
    my $reason = '';
    my $now = now_iso_utc();
    my @candidates;
    my $cj = File::Spec->catfile($pkt_dir, 'claim.json');
    push @candidates, $cj if is_file($cj);
    my $clj = File::Spec->catfile($pkt_dir, 'data', 'claims.jsonl');
    push @candidates, $clj if is_file($clj);
    for my $c (@candidates) {
        my $text = read_file_text($c);
        if ($c =~ /\.jsonl$/) {
            for my $line (split /\r?\n/, $text) {
                next unless $line =~ /\S/;
                my $claim = eval { decode_json($line) };
                next unless defined $claim;
                my $exp = $claim->{expires_at};
                if (defined $exp && $exp lt $now) {
                    $expired++;
                    $reason ||= "claim expires_at=$exp < now";
                }
            }
        } else {
            my $claim = eval { decode_json($text) };
            if (defined $claim) {
                my $exp = $claim->{expires_at};
                if (defined $exp && $exp lt $now) {
                    $expired++;
                    $reason ||= "claim expires_at=$exp < now";
                }
            }
        }
    }
    return {
        is => $expired > 0 ? 1 : 0,
        reason => $reason,
        count => $expired,
    };
}

# ---------- Verdict computation ----------
sub compute_verdict {
    my ($packet_path, $action_class) = @_;
    $action_class //= 'general';
    my $t0 = [gettimeofday()];
    my ($parseable, $parse_reason) = packet_is_parseable($packet_path);
    if (!$parseable) {
        return {
            verdict => $VERDICT{UNKNOWN},
            reasons => ['packet shape not parseable', $parse_reason],
            trust_dial_active => $IRREVERSIBLE{$action_class} ? 'Professional' : 'Casual',
            trust_dial_recommended_for_action_class => $TRUST_REC{$action_class} // 'Casual',
            top_3_signals => [{
                name => 'packet_parse', value => 'MALFORMED',
                civilian_phrasing => 'Packet shape could not be parsed.',
            }],
            signals => {},
            parse_status => 'malformed',
            action_class => $action_class,
            v15_extension => 'none',
            block_reason_id => 'UNKNOWN_PARSE_FAILURE',
            cache_hit => JSON::PP::false,
            elapsed_ms => sprintf('%.2f', tv_interval($t0) * 1000.0) + 0,
            doctor_version => $DOCTOR_VERSION,
        };
    }
    my $pkg_dir = is_dir($packet_path) ? $packet_path : File::Spec->catdir($packet_path, '..');

    my $q = detect_quarantined($pkg_dir);
    if ($q->{is}) {
        return {
            verdict => $VERDICT{QUARANTINED},
            reasons => ["policy violation: $q->{reason}", @{$q->{violations}}],
            trust_dial_active => 'Critical',
            trust_dial_recommended_for_action_class => 'Critical',
            top_3_signals => [{
                name => 'quarantine_violation', value => $q->{reason},
                civilian_phrasing => 'An explicit policy violation was detected. Review the audit log.',
            }],
            signals => extract_signals($pkg_dir),
            parse_status => 'parseable', action_class => $action_class,
            v15_extension => 'QUARANTINED', v15_evidence => $q->{violations},
            block_reason_id => 'QUARANTINED_POLICY_VIOLATION',
            cache_hit => JSON::PP::false,
            elapsed_ms => sprintf('%.2f', tv_interval($t0) * 1000.0) + 0,
            doctor_version => $DOCTOR_VERSION,
        };
    }

    my $c = detect_contested($pkg_dir);
    if ($c->{is}) {
        return {
            verdict => $VERDICT{CONTESTED},
            reasons => ["concurrent edits: $c->{reason}", @{$c->{evidence}}],
            trust_dial_active => 'Important',
            trust_dial_recommended_for_action_class => $TRUST_REC{$action_class} // 'Casual',
            top_3_signals => [{
                name => 'contested_concurrent_edit', value => $c->{reason},
                civilian_phrasing => 'Two or more edits to this packet conflict. Decide which wins before relying on this verdict.',
            }],
            signals => extract_signals($pkg_dir),
            parse_status => 'parseable', action_class => $action_class,
            v15_extension => 'CONTESTED', v15_evidence => $c->{evidence},
            block_reason_id => 'CONTESTED_CONCURRENT_EDIT',
            cache_hit => JSON::PP::false,
            elapsed_ms => sprintf('%.2f', tv_interval($t0) * 1000.0) + 0,
            doctor_version => $DOCTOR_VERSION,
        };
    }

    my $e = detect_expired($pkg_dir);
    if ($e->{is}) {
        return {
            verdict => $VERDICT{EXPIRED},
            reasons => ["TTL expired: $e->{reason}", "expired_count=$e->{count}"],
            trust_dial_active => 'Casual',
            trust_dial_recommended_for_action_class => $TRUST_REC{$action_class} // 'Casual',
            top_3_signals => [{
                name => 'expired_claims', value => $e->{count},
                civilian_phrasing => "$e->{count} claim(s) past their expiration date. Run the validator again to refresh them.",
            }],
            signals => extract_signals($pkg_dir),
            parse_status => 'parseable', action_class => $action_class,
            v15_extension => 'EXPIRED', v15_evidence => ["expired_count=$e->{count}", $e->{reason}],
            block_reason_id => 'EXPIRED_TTL',
            cache_hit => JSON::PP::false,
            elapsed_ms => sprintf('%.2f', tv_interval($t0) * 1000.0) + 0,
            doctor_version => $DOCTOR_VERSION,
        };
    }

    my $sigs = extract_signals($pkg_dir);
    my $f18 = $sigs->{f18_laundering_score}{score};
    my $f15 = $sigs->{f15_missing_witness_flag}{count};
    my $f16 = $sigs->{f16_attack_flag}{count};
    my $f19 = $sigs->{f19_coverage_gap_flag}{count};
    my $a8  = $sigs->{a8_srs_decay_status}{count};

    my @fail_reasons;
    push @fail_reasons, sprintf('F18 laundering score %.2f >= %.2f (CRITICAL)', $f18, $F18_FAIL) if $f18 >= $F18_FAIL;
    push @fail_reasons, "F15 missing-witness flag: $f15 criterion(a)" if $f15 >= 1;
    push @fail_reasons, "F16 attack class flag: $f16 attack(s)" if $f16 >= 1;
    my $fail_triggered = scalar(@fail_reasons) > 0;

    my @warn_reasons;
    push @warn_reasons, sprintf('F18 laundering score %.2f >= %.2f (HIGH-RISK)', $f18, $F18_WARN) if $f18 >= $F18_WARN && $f18 < $F18_FAIL;
    push @warn_reasons, "F19 coverage gap: $f19 missing" if $f19 >= 1;
    push @warn_reasons, "A8 SRS decay: $a8 stale claim(s)" if $a8 >= 1;
    my $warn_triggered = scalar(@warn_reasons) > 0;

    my ($verdict, @reasons);
    if ($fail_triggered) {
        $verdict = $VERDICT{FAIL}; @reasons = @fail_reasons;
    } elsif ($warn_triggered) {
        $verdict = $VERDICT{WARN}; @reasons = @warn_reasons;
    } elsif (!$sigs->{any_signal_non_ok}) {
        $verdict = $VERDICT{PASS}; @reasons = ('all F-tier signals clean');
    } else {
        $verdict = $VERDICT{WARN}; @reasons = scalar(@warn_reasons) > 0 ? @warn_reasons : ('minor signal flagged');
    }

    my $trust_dial_active =
        $IRREVERSIBLE{$action_class} ? 'Professional' :
        ($warn_triggered || $fail_triggered) ? 'Important' : 'Casual';

    my @candidates;
    push @candidates, {
        name => 'F18 laundering score',
        value => sprintf('%.2f', $f18) + 0,
        civilian_phrasing => $sigs->{f18_laundering_score}{civilian_phrasing},
    } if $f18 > 0;
    push @candidates, {
        name => 'F19 coverage gap', value => $f19,
        civilian_phrasing => "Skipped scope: $f19",
    } if $f19 > 0;
    push @candidates, {
        name => 'F15 completion gap', value => $f15,
        civilian_phrasing => "Hidden completion gap: $f15 detected",
    } if $f15 > 0;
    push @candidates, {
        name => 'F16 attack class', value => $f16,
        civilian_phrasing => "$f16 attack pattern(s) flagged",
    } if $f16 > 0;
    push @candidates, {
        name => 'A8 SRS decay', value => $a8,
        civilian_phrasing => "$a8 stale claim(s)",
    } if $a8 > 0;
    if (scalar(@candidates) == 0) {
        push @candidates, {
            name => 'all signals clean', value => 'OK',
            civilian_phrasing => 'No F-tier signals breached threshold.',
        };
    }
    my @top3 = @candidates[0 .. ($#candidates > 2 ? 2 : $#candidates)];

    my $block_reason_id = 'PASS_ALL_CLEAN';
    if ($verdict eq $VERDICT{FAIL}) {
        if ($f18 >= $F18_FAIL)    { $block_reason_id = 'F18_LAUNDERING_HIGH'; }
        elsif ($f15 >= 1)         { $block_reason_id = 'F15_MISSING_WITNESS'; }
        elsif ($f16 >= 1)         { $block_reason_id = 'F16_ATTACK_FLAG'; }
        else                      { $block_reason_id = 'F18_LAUNDERING_HIGH'; }
    } elsif ($verdict eq $VERDICT{WARN}) {
        $block_reason_id = 'WARN_SIGNAL_HIGH_NOT_CRITICAL';
    }

    return {
        verdict => $verdict,
        reasons => \@reasons,
        trust_dial_active => $trust_dial_active,
        trust_dial_recommended_for_action_class => $TRUST_REC{$action_class} // 'Casual',
        top_3_signals => \@top3,
        signals => $sigs,
        parse_status => 'parseable',
        action_class => $action_class,
        v15_extension => 'none',
        block_reason_id => $block_reason_id,
        cache_hit => JSON::PP::false,
        elapsed_ms => sprintf('%.2f', tv_interval($t0) * 1000.0) + 0,
        doctor_version => $DOCTOR_VERSION,
    };
}

# ---------- Canonical projection (byte-parity fingerprint) ----------
sub canonical_projection {
    my ($rec) = @_;
    my $signals = $rec->{signals} || {};
    return {
        action_class => $rec->{action_class},
        block_reason_id => $rec->{block_reason_id},
        parse_status => $rec->{parse_status},
        reasons => $rec->{reasons},
        signals_summary => {
            f15_missing_witness_count => ($signals->{f15_missing_witness_flag} // {})->{count} // 0,
            f16_attack_count => ($signals->{f16_attack_flag} // {})->{count} // 0,
            f18_laundering_score_str => sprintf('%.2f', ($signals->{f18_laundering_score} // {})->{score} // 0),
            f19_coverage_gap_count => ($signals->{f19_coverage_gap_flag} // {})->{count} // 0,
            a8_srs_decay_count => ($signals->{a8_srs_decay_status} // {})->{count} // 0,
            any_signal_non_ok => ($signals->{any_signal_non_ok} ? JSON::PP::true : JSON::PP::false),
        },
        top_3_signals_names => [map { $_->{name} } @{$rec->{top_3_signals} // []}],
        trust_dial_active => $rec->{trust_dial_active},
        trust_dial_recommended_for_action_class => $rec->{trust_dial_recommended_for_action_class},
        v15_extension => $rec->{v15_extension},
        verdict => $rec->{verdict},
    };
}

sub canonical_sha256 {
    my ($obj) = @_;
    my $json = JSON::PP->new->utf8->canonical(1);
    my $canon = $json->encode($obj);
    return sha256_hex($canon);
}

# ---------- Exit codes ----------
sub exit_for_verdict {
    my ($v) = @_;
    my %map = (
        PASS => 0, WARN => 1, FAIL => 2, UNKNOWN => 3,
        EXPIRED => 4, CONTESTED => 5, QUARANTINED => 6,
    );
    return $map{$v} // 3;
}

# ---------- CLI ----------
sub main {
    my $packet;
    my $as_json = 0;
    my $quiet = 0;
    my $canonical = 0;
    my $action_class = 'general';
    my @args = @ARGV;
    while (@args) {
        my $a = shift @args;
        if    ($a eq '--json') { $as_json = 1; }
        elsif ($a eq '--quiet') { $quiet = 1; }
        elsif ($a eq '--no-cache') { } # no-op
        elsif ($a eq '--canonical') { $canonical = 1; }
        elsif ($a eq '--action-class') { $action_class = shift @args; }
        elsif (!defined $packet) { $packet = $a; }
    }

    unless (defined $packet) {
        print STDERR "Usage: perl aep_doctor_perl.pl <packet> [--json] [--canonical] [--quiet] [--action-class CLASS]\n";
        return 2;
    }

    my $rec = compute_verdict($packet, $action_class);
    my $json = JSON::PP->new->utf8->canonical(1);

    if ($canonical) {
        my $proj = canonical_projection($rec);
        my $hash = canonical_sha256($proj);
        my $out = {
            canonical_projection => $proj,
            canonical_sha256 => $hash,
            doctor_version => $DOCTOR_VERSION,
        };
        print $json->pretty->encode($out) unless $quiet;
        return exit_for_verdict($rec->{verdict});
    }

    if ($as_json) {
        print $json->pretty->encode($rec) unless $quiet;
    } else {
        unless ($quiet) {
            print "VERDICT: $rec->{verdict}\n";
            print "Trust level: $rec->{trust_dial_active}\n";
            print "Block reason: $rec->{block_reason_id}\n";
            print "Elapsed: $rec->{elapsed_ms} ms ($rec->{doctor_version})\n";
        }
    }
    return exit_for_verdict($rec->{verdict});
}

exit main() unless caller;
