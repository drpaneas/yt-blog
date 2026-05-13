# Software Should Be Perfect

## In this post

- What "perfect software" actually means — and why a JavaScript addition function already fails the standard
- Why memory allocation failure disqualifies most programming languages from ever producing fully correct software
- How Zig makes error handling mandatory but ergonomic, with live-coded examples from the first public talk about the language
- Why Zig's compile-time execution produced a SHA-256 implementation that benchmarked faster than hand-optimized C and x86 assembly
- How Zig interoperates with C libraries directly and cross-compiles for any target from any host

Source: https://www.youtube.com/watch?v=Z4oYSByyRak

## What "perfect" means

Andrew Kelley, the creator of [Zig](https://ziglang.org/), opened the first-ever public talk about the language at the [Recurse Center](https://www.recurse.com/) in March 2018 with a provocation: software should be perfect. No bugs. No exceptions. It works every time.

He then offered a working definition: perfect software is code where you define your set of inputs, and for every single possible input, the code produces the correct output.

Start with the trivial case. A C function that computes boolean NOT:

```c
bool not(bool x) {
    return !x;
}
```

Two inputs, two correct outputs. This is perfect software.

Now try addition in JavaScript:

```javascript
function add(a, b) {
    return a + b;
}

add(9007199254740992, 1)
// returns 9007199254740992 — not 9007199254740993
```

The result is off by one. JavaScript uses 64-bit floating-point for all numbers, and at this magnitude the format cannot represent consecutive integers. The `add` function is correct code that produces wrong output. We have already left the domain of perfect software.

Switch to C++. A function that concatenates two strings:  

```cpp
std::string concatStrings(std::string lhs, std::string rhs) {
    return lhs + rhs;
}
```

Concatenation might need to allocate a bigger buffer. If the system is at memory capacity, this throws `std::bad_alloc`. You could define the function so that the exception is a documented possible output — fine, call it perfect. But now try using that function to build a larger system. The caller has no indication in the type signature that string concatenation can throw. Building perfect software on top of this gets very hard, very fast.

Python solves the integer addition problem by using arbitrary-precision integers. But its big-number arithmetic allocates memory under the hood, and memory allocation can fail. Same problem.

## The over-commit trap

Before getting to the language, Kelley spent time on a piece of operating system behavior that undermines any attempt at correct memory handling: over-commit.

Over-commit is when the OS promises more memory than it physically has. On Linux with over-commit enabled:

```c
void *p = malloc(10 * 1024 * 1024);  // 10 MB
// malloc returns a valid pointer, even if no physical memory is left
// The failure comes later, when you write to p:
memset(p, 0, 10 * 1024 * 1024);
// OOM killer fires and terminates a process — not necessarily yours
```

With over-commit off, `malloc` returns null and you handle it. With over-commit on, `malloc` succeeds, but writing to the memory triggers the OOM killer, which picks a process to kill. Not necessarily the one that asked for memory. Any process on the system.

Kelley gave two real-world examples. He called a Lyft on his Android phone, switched to a map app, and the OOM killer rebooted his phone — the Lyft driver arrived while the phone was restarting. In another case, he was building Clang in debug mode, ran out of memory during the link step, and the OOM killer killed his window manager instead of the compiler, destroying everything he was working on.

But over-commit is not universal. It is configurable on Linux, absent on Windows, and off on most production servers where per-process memory limits cause `malloc` to fail directly. Kelley's premise: any language aspiring to perfect software must assume that memory allocation can fail.

## Hidden allocations disqualify most languages

With that premise, Kelley went through the language landscape and disqualified almost everything.

In JavaScript, creating a closure allocates on the heap:

```javascript
function counter() {
    let x = 0;
    return function() { return x++; };
}
```

That closure captures `x`, which requires a heap allocation. If the allocation fails, JavaScript provides no mechanism to handle it. The same problem applies to Python, Ruby, Perl, PHP, Haskell, Lisp, Swift, Nim, and Go. All of them perform hidden memory allocations that the programmer cannot intercept.

Languages with exceptions — Java, C#, C++, D — technically offer a mechanism. You could catch `std::bad_alloc` or `OutOfMemoryError`. But Kelley's argument is that nobody does this reliably. People compile C++ with `-fno-exceptions`. Java code routinely catches `Exception` at the top level and discards it. Exception-based error handling has not produced software that correctly handles every allocation failure.

Cross those off. You are left with C, which has been the answer for 45 years.

## Enter Zig

This is why Zig exists. When Kelley presented the language's feature list, the pitch was broad:

- Compiles faster than C
- Produces faster machine code than C
- Seamless interaction with C libraries
- Robust and ergonomic error handling
- Compile-time code execution and reflection
- Generics
- async, await, promises via coroutines
- No hidden control flow
- No hidden memory allocations
- Ships with build system
- Out-of-the-box cross compilation on any system, for any system

But the core of the talk — and the reason the language was built — was the error handling story. Kelley demonstrated it live, building up from a hello world.

### The starting point

He opened a file called `errors.zig` in vim and wrote a hello world:

```zig
const std = @import("std");

pub fn main() void {
    std.debug.warn("hello\n");
}
```

Then he introduced a memory allocator. In most languages, memory allocation is hidden behind `new` or the runtime. In Zig, allocators are explicit — you choose one and pass it to anything that needs memory. For the demo, Kelley used a pre-allocated 200-kilobyte block:

```zig
const std = @import("std");

pub fn main() void {
    const integers = std.debug.global_allocator.alloc(i32, 100);
    integers[10] = 1234;
}
```

This does not compile:

```
error: expression value is ignored
    const integers = std.debug.global_allocator.alloc(i32, 100);
                     ^
note: error is ignored; must be handled with `catch` or `try`
```

The return type of `alloc` includes the possibility of an error, and the language refuses to let you proceed without handling it.

### Catch

The first way to handle it is with `catch`:

```zig
const std = @import("std");

pub fn main() void {
    const integers = std.debug.global_allocator.alloc(i32, 100) catch |e| {
        std.debug.warn("out of memory\n");
        return;
    };
    integers[10] = 1234;
}
```

The `catch` block runs if the allocation fails. Inside it, you can print a message, clean up, return, or do whatever makes sense. This version compiles and runs fine — the 200-kilobyte allocator has plenty of room for 100 integers.

### Try

The common case is simpler: if allocation fails, propagate the error to the caller. The `try` keyword does exactly that:

```zig
const std = @import("std");

pub fn main() !void {
    const integers = try std.debug.global_allocator.alloc(i32, 100);
    integers[10] = 1234;
}
```

Two things changed. The return type of `main` became `!void` — the `!` means the function can now return an error. And `try` replaced the entire `catch` block. It says: if this fails, return the error from my function; otherwise, give me the value.

When Kelley changed the allocation to request far more than the 200KB allocator could provide:

```zig
const integers = try std.debug.global_allocator.alloc(i32, 100000000);
```

The program output:

```
error: OutOfMemory
/usr/lib/zig/std/debug/global_allocator.zig:12:37: 0x203fe4 in alloc
    return error.OutOfMemory;
                             ^
./errors.zig:4:49: 0x2035f2 in main
    const integers = try std.debug.global_allocator.alloc(i32, 100000000);
                                                    ^
```

The stack trace shows exactly where the allocation failed and how the error propagated up through `main`.

### Error return traces

To demonstrate what diagnostic information looks like at scale, Kelley opened the Zig compiler's own source code and injected a block that made every allocation fail with a 1-in-255 chance. Then he ran the compiler's build process.

It crashed, as expected. But the output contained two pieces of information:

1. An **error return trace** — showing the path the error took from its origin (the allocation that failed) through every function that propagated it with `try`
2. A **stack trace** — showing the conventional call stack at the point of the crash

These two traces connect: the end of the error return trace is the beginning of the stack trace. You can read the complete failure path as a single narrative, from the original allocation failure through every `try` that passed it upward, to the point where code asserted `catch unreachable` — a promise to the compiler that the error would never happen. Since the build was compiled in debug mode, the compiler said: you told me this was unreachable, but I got here, and here is exactly why.

No debugger needed. The information was right there in the crash output.

## Faster machine code than C

Kelley claimed that Zig produces faster machine code than C. He acknowledged this sounds improbable — languages normally measure their speed as a fraction of C's. "I'm telling you that it's an improper fraction," he said.

The benchmark was SHA-256. A Zig contributor named Mark Thomas implemented the algorithm by studying an Intel optimization guide and a reference C implementation that included hand-rolled x86-64 assembly. The results, run on stage on Kelley's laptop:

| Implementation | Throughput |
|---|---|
| C (reference) | 180 MB/s |
| Hand-rolled x86-64 assembly | 192 MB/s |
| Zig | 205 MB/s |

The Zig implementation was 14% faster than the hand-optimized assembly. Both the C and Zig versions used LLVM as their backend, so the difference was not in the optimizer but in the intermediate representation each language fed it.

The gap came from Zig's `comptime`. The SHA-256 implementation used compile-time evaluation to initialize lookup tables and unroll loops. Because the loop bounds and table values were compile-time known, Zig's LLVM IR exposed more optimization opportunities. Kelley showed the generated assembly side by side - the Zig version used the `rorx` instruction from Intel's BMI2 extension, which the C version's IR did not trigger:

```asm
; C version: rotate via shift+or
mov eax, edx
shr eax, 6
shl edx, 26
or  eax, edx

; Zig version: single instruction
rorx eax, edx, 6
```

One instruction instead of four, and the CPU can schedule it more efficiently.

## Compile-time code execution

Zig's `comptime` keyword lets you run arbitrary Zig code during compilation. Not a preprocessor, not a template system — the same language, evaluated at compile time.

Kelley's demo was a small program with two functions: one that computes the first N prime numbers, and one that sums a list. At the top level, a compile-time assertion checked that the sum of the first 25 primes equals 1060:

```zig
fn firstNPrimes(comptime n: usize) [n]u32 {
    var primes: [n]u32 = undefined;
    var i: u32 = 2;
    var count: usize = 0;
    while (count < n) : (i += 1) {
        var is_prime = true;
        for (primes[0..count]) |p| {
            if (i % p == 0) {
                is_prime = false;
                break;
            }
        }
        if (is_prime) {
            primes[count] = i;
            count += 1;
        }
    }
    return primes;
}

fn sum(list: []const u32) u32 {
    var total: u32 = 0;
    for (list) |x| total += x;
    return total;
}

comptime {
    std.debug.assert(sum(&firstNPrimes(25)) == 1060);
}
```

The program compiled successfully — the assertion passed at compile time. The resulting binary contained only the pre-computed constants. Neither function was included in the binary, because neither was called at runtime.

When Kelley changed 1060 to 1061:

```
error: comptime evaluation reached unreachable: assertion failure
    std.debug.assert(sum(&firstNPrimes(25)) == 1061);
    ^
```

When he removed the loop condition to create an infinite loop:

```
error: evaluation exceeded 1000 backwards branches
```

The iteration limit is configurable - a pragmatic solution to the halting problem.

## C interop and cross-compilation

Zig imports C header files directly and calls C functions without writing bindings. Kelley demonstrated a Tetris game built with OpenGL, libPNG, and GLFW — all C libraries. The Zig code imported the `.h` files and called the C API directly:

```zig
const c = @cImport({
    @cInclude("GL/gl.h");
    @cInclude("GLFW/glfw3.h");
});

// Then call c.glGetAttribLocation, c.glGetUniformLocation, etc.
```

Zig understands many `#define` macros — the ones that resolve to constants or simple expressions — so common C idioms work without manual translation. The interop goes both ways: Zig libraries can export C-compatible headers.

For the most dramatic demo, Kelley cross-compiled a user-land program for a microkernel operating system built by a Recurse Center alum. He built the entire OS on his laptop, ran it inside QEMU, then compiled a "hello world" from Zig's source repository targeting that OS, and ran it inside the emulated kernel. The same Zig source code that works on Linux, Windows, and macOS ran on a hobby microkernel, cross-compiled from a different architecture.

## The Zen of Zig

During the Q&A, someone asked what criteria Kelley used to decide what belongs in the standard library. He pulled up the project's design philosophy from the documentation:

- Communicate intent precisely.
- Edge cases matter.
- Favor reading code over writing code.
- Only one obvious way to do things.
- Runtime crashes are better than bugs.
- Compile errors are better than runtime crashes.
- Incremental improvements.
- Avoid local maximums.
- Reduce the amount one must remember.
- Minimize energy spent on coding style.
- Together we serve end users.

Two of these principles were especially visible throughout the talk. "Edge cases matter" was the entire premise — allocation failure is an edge case most languages ignore. "Favor reading code over writing code" explained why Kelley refuses most feature proposals. People propose syntax shortcuts and convenience mechanisms, and even the good ones add a concept every reader must understand. Zig's value is partly that the language is small enough to hold in your head: structs, functions, and not much else — C minus the preprocessor, with a few well-chosen additions.

On recursion, Kelley noted it is "one of the enemies of perfect software" because it makes static stack size analysis impossible. He was considering ways to annotate recursive functions so the compiler could check stack requirements, or to make recursion fallible — a recursive call might fail if stack space is exhausted. The problem was unsolved, but he had plans for static call graph analysis that would let the compiler compute exact stack requirements and request precisely that amount from the OS.

## Where Rust fits

Someone asked about Rust. Kelley was direct: Rust is Zig's main competitor, and it is a great project.

On allocation failure specifically, he noted that Rust's standard library used to panic on allocation failure:

```rust
let mut v = Vec::new();
v.push(42); // panics if allocation fails — no way to handle it
```

By the time of this talk, Rust had added `try_reserve` methods to containers, allowing callers to handle allocation failure without panicking. Kelley described the additions as "kind of like bike lanes in New York City - but it does the job."

The short version: you can write correct, allocation-aware software in Rust. Zig's pitch is that its entire standard library was designed around explicit allocation from the start, rather than retrofitting it.

## Takeaways

This talk was given when Zig was at version 0.2.0 — seven active contributors, about 35 people in the IRC channel. The language has grown substantially since, but the ideas Kelley laid out transfer beyond any single language:

- **Allocation failure is not an edge case you can ignore.** Any language that hides memory allocation from the programmer makes it structurally impossible to handle exhaustion. If your software runs in constrained environments — embedded systems, production servers with memory limits, mobile devices — this matters.
- **Error handling must be cheaper than ignoring errors.** Zig's `try` is one keyword. Ignoring an error is a compile error. When the correct path requires less effort than the incorrect one, developers take the correct path.
- **Compile-time execution is a multiplier.** A single mechanism — evaluating the language itself at compile time — replaces the preprocessor, enables generics, validates format strings, and gives the optimizer better material to work with. The SHA-256 benchmark was a concrete demonstration: compile-time knowledge enabled optimizations that hand-tuned assembly did not achieve.
- **Language simplicity is a feature.** Every feature added is a concept every reader must know. Refusing features — even good ones — is what keeps a language readable. The Zen of Zig puts it directly: favor reading code over writing code.
- **Start from a real problem.** Kelley was building a peer-to-peer music studio and ran into problems with concurrency, performance, and tooling. He concluded the available languages were inadequate, took a break to write a compiler — because, as he put it, that was easier than writing a peer-to-peer music studio — and Zig is the result.
