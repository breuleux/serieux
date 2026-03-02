# serieux

(The README is a work in progress)

Serieux is a very extensible composable serialization/configuration library for Python. Based on [ovld](https://github.com/breuleux/ovld)'s extensive multiple dispatch and code generation, Serieux has many features and makes it possible to define many more with little interference with the rest of the system.

[📋 Documentation](https://serieux.readthedocs.io/en/latest/)

## Features

### Configuration

Serieux has many features that pertain directly to human-writable configuration:

* **Merge multiple sources**: seamlessly merge information from multiple files, formats, dictionaries
* **Include files**: (optional) include configuration files from configuration files to better separate concerns
* **Variable interpolation**: (optional) interpolate and environment variables and data from elsewhere in the configuration
* **Encrypt fields**: fields marked as `Secret[T]` can be set directly in the configuration and encrypted using the command `serieux patch <file>`
* **Dotted notation**: (optional) allow keys of the form `x.y.z` instead of nesting data

All of the aforementioned features should work with each other (although there may still be some bugs, the more of them you combine). For instance, you can merge and encrypt fields through file inclusions, you can determine which file to include through a variable interpolation, and so on.

### Types

* **Tagged types:** tagged types use the `$class` property to determine the deserialization type
  * **`TaggedUnion[T1, T2, ...]`**: Define auto-named tagged unions of multiple types (type information goes in `$class`)
  * **`TaggedSubclass[T]`**: Point to any subclass of T
  * **`TaggedSubclass[Any]`**: Point to any constructor at all
* **`Referenced[T]`**: Deserialize `some_module:some_symbol` into the referenced symbol
* **`Lazy[T]`**: Proxy data of type T so that it is only loaded when accessed
* **`Comment[DT, CT]`**: Allow data of type DT to be commented by data with type CT
