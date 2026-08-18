// Copyright © 2026 & onwards, Alessandro Di Ronza <ales.drnz@gmail.com>.
// All rights reserved.
// Use of this source code is governed by BSD 3-Clause license that can be found in the LICENSE file.

package main

import "testing"

func TestClassify(t *testing.T) {
	cases := []struct {
		line string
		want logClass
	}{
		{"lib/socket.c:12:3: error: expected ';'", clErr},
		{"fatal error: config.h: No such file or directory", clErr},
		{"undefined reference to `smb2_utimes'", clErr},
		{"lib/pdu.c:88:5: warning: unused variable", clWarn},
		{"▶ Linux x86_64", clInfo},
		{"✓ linux-x86_64", clInfo},
		{"checking for error_at_line... yes", clNone},
		{"  gcc -c lib/errors.c -o errors.o", clNone},
		{"-Werror was not passed", clNone},
	}
	for _, c := range cases {
		if got := classify(c.line); got != c.want {
			t.Errorf("classify(%q) = %d, want %d", c.line, got, c.want)
		}
	}
}

func TestCountersAdd(t *testing.T) {
	var c counters
	c.add(clInfo)
	c.add(clWarn)
	c.add(clWarn)
	c.add(clErr)
	c.add(clNone)
	if c.info != 1 || c.warn != 2 || c.errs != 1 {
		t.Errorf("counters = %+v, want info=1 warn=2 errs=1", c)
	}
}
